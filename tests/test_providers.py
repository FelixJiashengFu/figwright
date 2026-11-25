"""Model providers, against fake servers.

No test here talks to a real provider or uses a real key: each dialect is
answered by a local handler, so what is checked is our side of the contract,
including what happens when the answer is wrong, truncated or an error.
"""

from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

from figwright import config
from figwright.providers import ProviderError, make_provider
from figwright.providers.base import data_url, scrub, sniff_image_type
from figwright.providers.gemini import GeminiProvider
from figwright.providers.mock import MockProvider
from figwright.providers.openai_compat import OpenAICompatProvider

KEY = "test-not-a-real-key-0000"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


def transport(handler):
    """Wrap a function of (request) -> httpx.Response as a transport."""
    return httpx.MockTransport(handler)


# ------------------------------------------------------------------ small helpers


def test_an_image_type_is_sniffed_from_the_bytes():
    assert sniff_image_type(PNG) == "image/png"
    assert sniff_image_type(b"\xff\xd8\xff\xe0 jpeg") == "image/jpeg"
    assert sniff_image_type(b"RIFF0000WEBPVP8 ") == "image/webp"
    assert sniff_image_type(b"nonsense") == "image/png"  # a sane default


def test_a_data_url_round_trips():
    url = data_url(PNG)
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == PNG


def test_a_key_is_never_echoed_back_in_an_error():
    assert scrub(f"failed with key {KEY}", KEY) == "failed with key [key]"
    assert scrub("no key here", KEY) == "no key here"
    assert scrub("text", None) == "text"


# ------------------------------------------------------------------ offline demo provider


def test_the_offline_demo_says_it_has_no_language_model():
    """Demo mode does not pretend: the caller falls back to the text rules."""
    p = MockProvider({"id": "mock", "type": "mock", "model": ""})
    with pytest.raises(ProviderError) as err:
        p.chat("system", "采样、提取、测序")
    assert err.value.code == "unsupported"
    # It can still stand in for an image model, with an obvious placeholder.
    assert p.generate_image("a cell")[:8] == b"\x89PNG\r\n\x1a\n"
    assert p.list_models() == [] or isinstance(p.list_models(), list)


def test_make_provider_refuses_a_provider_with_no_key():
    with pytest.raises(ProviderError) as err:
        make_provider({"id": "openai", "type": "openai", "needs_key": True, "api_key": "", "base_url": "https://x/v1"})
    assert "key" in str(err.value).lower()


def test_make_provider_refuses_an_unknown_type():
    with pytest.raises(ProviderError):
        make_provider({"id": "x", "type": "telepathy"})


# ------------------------------------------------------------------ OpenAI-compatible


def openai_handler(reply="{\"nodes\": []}", finish="stop", status=200, body=None, capture=None):
    def handle(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        if status != 200:
            return httpx.Response(status, json=body or {"error": {"message": "nope"}})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "model-b"}, {"id": "model-a"}]})
        if "images" in request.url.path:
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(PNG).decode()}]})
        return httpx.Response(200, json={
            "model": "model-a",
            "choices": [{"message": {"content": reply}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 22},
        })

    return handle


def openai(**kw):
    return OpenAICompatProvider(
        {"id": "custom", "type": "openai", "api_key": KEY, "base_url": "https://api.example.test/v1", "model": "model-a"},
        transport=transport(openai_handler(**kw)),
    )


def test_a_chat_answer_comes_back_with_its_usage():
    out = openai().chat("be brief", "hello")
    assert out.text == '{"nodes": []}'
    assert out.usage["input_tokens"] == 11 and out.usage["output_tokens"] == 22
    assert out.model == "model-a" and not out.truncated


def test_the_key_is_sent_as_a_bearer_token_and_nothing_else_is():
    seen: list[httpx.Request] = []
    p = OpenAICompatProvider(
        {"id": "custom", "type": "openai", "api_key": KEY, "base_url": "https://api.example.test/v1", "model": "model-a"},
        transport=transport(openai_handler(capture=seen)),
    )
    p.chat("s", "u")
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(seen[0].content)
    assert body["model"] == "model-a"
    assert [m["role"] for m in body["messages"]] == ["system", "user"]


def test_an_image_is_sent_as_a_data_url():
    seen: list[httpx.Request] = []
    p = OpenAICompatProvider(
        {"id": "custom", "type": "openai", "api_key": KEY, "base_url": "https://api.example.test/v1", "model": "m"},
        transport=transport(openai_handler(capture=seen)),
    )
    p.chat("s", "describe", images=[PNG])
    parts = json.loads(seen[0].content)["messages"][-1]["content"]
    assert any(part.get("type") == "image_url" for part in parts)
    assert any("data:image/png;base64," in json.dumps(part) for part in parts)


def test_a_truncated_answer_is_flagged():
    out = openai(finish="length").chat("s", "u")
    assert out.truncated


def test_models_come_back_sorted():
    assert openai().list_models() == ["model-a", "model-b"]


def test_an_image_is_decoded_from_base64():
    assert openai().generate_image("a cell")[:4] == PNG[:4]


@pytest.mark.parametrize("status,code", [(401, "auth"), (403, "permission"), (404, "not_found"), (429, "rate_limit"), (400, "bad_request"), (500, "server")])
def test_each_http_error_gets_a_useful_code(status, code):
    with pytest.raises(ProviderError) as err:
        openai(status=status).chat("s", "u")
    assert err.value.code == code
    assert KEY not in str(err.value)


def test_a_network_failure_says_so():
    def boom(request):
        raise httpx.ConnectError("no route", request=request)

    p = OpenAICompatProvider(
        {"id": "custom", "type": "openai", "api_key": KEY, "base_url": "https://api.example.test/v1", "model": "m"},
        transport=transport(boom),
    )
    with pytest.raises(ProviderError) as err:
        p.chat("s", "u")
    assert err.value.code == "network"


def test_an_answer_with_no_choices_is_an_error_not_a_crash():
    def handle(request):
        return httpx.Response(200, json={"choices": []})

    p = OpenAICompatProvider(
        {"id": "c", "type": "openai", "api_key": KEY, "base_url": "https://api.example.test/v1", "model": "m"},
        transport=transport(handle),
    )
    with pytest.raises(ProviderError):
        p.chat("s", "u")


def test_html_instead_of_json_is_reported_clearly():
    def handle(request):
        return httpx.Response(200, text="<html>Gateway</html>", headers={"content-type": "text/html"})

    p = OpenAICompatProvider(
        {"id": "c", "type": "openai", "api_key": KEY, "base_url": "https://api.example.test/v1", "model": "m"},
        transport=transport(handle),
    )
    with pytest.raises(ProviderError) as err:
        p.chat("s", "u")
    assert "json" in str(err.value).lower() or "html" in str(err.value).lower()


# ------------------------------------------------------------------ Gemini


def gemini_handler(text='{"nodes": []}', status=200):
    def handle(request: httpx.Request) -> httpx.Response:
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "nope"}})
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"models": [{"name": "models/gemini-test", "supportedGenerationMethods": ["generateContent"]}]})
        return httpx.Response(200, json={
            "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 7},
        })

    return handle


def gemini(**kw):
    return GeminiProvider(
        {"id": "gemini", "type": "gemini", "api_key": KEY, "base_url": "https://gen.example.test/v1beta", "model": "gemini-test"},
        transport=transport(gemini_handler(**kw)),
    )


def test_gemini_answers_and_reports_usage():
    out = gemini().chat("sys", "hi")
    assert out.text == '{"nodes": []}'
    assert out.usage["input_tokens"] == 5 and out.usage["output_tokens"] == 7


def test_gemini_models_are_listed_without_their_prefix():
    assert gemini().list_models() == ["gemini-test"]


def test_gemini_errors_are_translated():
    with pytest.raises(ProviderError) as err:
        gemini(status=429).chat("s", "u")
    assert err.value.code == "rate_limit"


def test_the_gemini_key_goes_in_a_header_not_the_url():
    seen: list[httpx.Request] = []

    def handle(request):
        seen.append(request)
        return gemini_handler()(request)

    p = GeminiProvider(
        {"id": "gemini", "type": "gemini", "api_key": KEY, "base_url": "https://gen.example.test/v1beta", "model": "m"},
        transport=transport(handle),
    )
    p.chat("s", "u")
    assert KEY not in str(seen[0].url)
    assert seen[0].headers.get("x-goog-api-key") == KEY


# ------------------------------------------------------------------ Anthropic, through the real SDK


class Handler(BaseHTTPRequestHandler):
    """Enough of the Messages API to answer the SDK: it streams, so we stream."""

    text = '{"nodes": []}'
    status = 200
    stop_reason = "end_turn"

    def _json(self, body: dict, status: int = 200) -> None:
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _event(self, name: str, data: dict) -> None:
        self.wfile.write(f"event: {name}\ndata: {json.dumps(data)}\n\n".encode())

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length") or 0)
        type(self).last = json.loads(self.rfile.read(length) or b"{}")
        # Which header carries the key is the SDK's business, so take either.
        type(self).auth = self.headers.get("x-api-key") or (self.headers.get("authorization") or "").removeprefix("Bearer ")
        type(self).path_seen = self.path
        if type(self).status != 200:
            self._json({"type": "error", "error": {"type": "overloaded_error", "message": "busy"}}, type(self).status)
            return
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.end_headers()
        message = {"id": "msg_test", "type": "message", "role": "assistant", "model": "claude-test",
                   "content": [], "stop_reason": None, "stop_sequence": None,
                   "usage": {"input_tokens": 3, "output_tokens": 0}}
        self._event("message_start", {"type": "message_start", "message": message})
        self._event("content_block_start", {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
        self._event("content_block_delta", {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": type(self).text}})
        self._event("content_block_stop", {"type": "content_block_stop", "index": 0})
        self._event("message_delta", {"type": "message_delta", "delta": {"stop_reason": type(self).stop_reason, "stop_sequence": None}, "usage": {"output_tokens": 4}})
        self._event("message_stop", {"type": "message_stop"})

    def do_GET(self) -> None:  # noqa: N802
        self._json({"data": [{"id": "claude-test", "type": "model"}], "has_more": False})

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def anthropic_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    Handler.status = 200
    Handler.stop_reason = "end_turn"
    Handler.text = '{"nodes": []}'
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def anthropic_provider(base_url, model="claude-test"):
    return make_provider({"id": "anthropic", "type": "anthropic", "needs_key": True, "api_key": KEY,
                          "base_url": base_url, "model": model})


def test_the_anthropic_client_talks_to_the_messages_api(anthropic_server):
    p = anthropic_provider(anthropic_server)
    out = p.chat("be brief", "hello")
    assert out.text == '{"nodes": []}'
    assert out.usage == {"input_tokens": 3, "output_tokens": 4}
    assert out.model == "claude-test" and not out.truncated
    assert Handler.auth == KEY
    assert Handler.last["system"] == "be brief"
    assert Handler.last["messages"] == [{"role": "user", "content": "hello"}]
    assert Handler.last["stream"] is True
    p.close()


def test_a_current_model_is_asked_for_an_effort_level(anthropic_server):
    p = anthropic_provider(anthropic_server, model="claude-opus-5-5")
    p.chat("s", "u")
    assert Handler.last.get("output_config") == {"effort": "medium"}
    # budget_tokens is rejected by these models, so it must not be sent.
    assert "budget_tokens" not in json.dumps(Handler.last)
    assert Handler.last["max_tokens"] > 8192  # room for thinking
    p.close()


def test_an_older_model_does_not_get_the_new_fields(anthropic_server):
    p = anthropic_provider(anthropic_server, model="claude-3-5-sonnet-20241022")
    p.chat("s", "u")
    assert "output_config" not in Handler.last and "thinking" not in Handler.last
    assert Handler.last["max_tokens"] <= 8192
    p.close()


def test_an_answer_cut_off_at_the_limit_is_flagged(anthropic_server):
    Handler.stop_reason = "max_tokens"
    p = anthropic_provider(anthropic_server)
    assert p.chat("s", "u").truncated
    p.close()


def test_a_refusal_is_its_own_kind_of_error(anthropic_server):
    Handler.stop_reason = "refusal"
    p = anthropic_provider(anthropic_server)
    with pytest.raises(ProviderError) as err:
        p.chat("s", "u")
    assert err.value.code == "refusal"
    p.close()


def test_an_empty_answer_is_an_error(anthropic_server):
    Handler.text = "   "
    p = anthropic_provider(anthropic_server)
    with pytest.raises(ProviderError) as err:
        p.chat("s", "u")
    assert err.value.code == "empty"
    p.close()


def test_an_image_is_sent_as_base64_to_anthropic(anthropic_server):
    p = anthropic_provider(anthropic_server)
    p.chat("s", "look", images=[PNG])
    blocks = Handler.last["messages"][0]["content"]
    assert blocks[0]["type"] == "image" and blocks[0]["source"]["media_type"] == "image/png"
    assert base64.b64decode(blocks[0]["source"]["data"]) == PNG
    assert blocks[-1] == {"type": "text", "text": "look"}
    p.close()


def test_an_overloaded_server_is_reported_as_such(anthropic_server):
    Handler.status = 529
    p = anthropic_provider(anthropic_server)
    with pytest.raises(ProviderError) as err:
        p.chat("s", "u")
    assert err.value.code in ("server", "rate_limit", "overloaded")
    assert KEY not in str(err.value)
    p.close()


def test_models_can_be_listed(anthropic_server):
    p = anthropic_provider(anthropic_server)
    assert "claude-test" in p.list_models()
    p.close()


# ------------------------------------------------------------------ settings


def test_a_key_is_stored_and_only_ever_shown_masked():
    cfg = config.load_config()
    cfg = config.update_config(cfg, {"providers": {"openai": {"api_key": KEY}}})
    config.save_config(cfg)
    again = config.load_config()
    assert config.provider_settings(again, "openai")["api_key"] == KEY
    public = config.public_config(again)
    assert KEY not in json.dumps(public)
    row = next(p for p in public["providers"] if p["id"] == "openai")
    assert row["key_set"] is True and row["key_hint"] == config.mask_key(KEY)
    assert config.mask_key(KEY) != KEY and KEY[-4:] in config.mask_key(KEY)


def test_the_config_file_is_not_world_readable():
    config.save_config(config.load_config())
    assert oct(config.config_path().stat().st_mode)[-3:] == "600"


def test_a_key_in_the_environment_is_used_when_none_is_stored(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "from-env-key-1234")
    settings = config.provider_settings(config.load_config(), "openai")
    assert settings["api_key"] == "from-env-key-1234"
    assert settings["key_from_env"] is True


def test_a_base_url_must_be_http_and_not_a_credential_carrier():
    assert config.check_base_url("https://api.example.com/v1") == "https://api.example.com/v1"
    for bad in ("ftp://x/v1", "file:///etc", "not a url", "https://user:pw@api.example.com/v1", "javascript:alert(1)"):
        with pytest.raises(config.ConfigError):
            config.check_base_url(bad)


def test_a_local_address_is_allowed_for_ollama_and_friends():
    for ok in ("http://localhost:11434/v1", "http://127.0.0.1:1234/v1"):
        assert config.check_base_url(ok) == ok


def test_a_role_falls_back_to_a_provider_that_can_do_the_job():
    cfg = config.load_config()
    cfg = config.update_config(cfg, {"roles": {"text": {"provider": "mock", "model": ""}}})
    assert config.role_settings(cfg, "text")["type"] == "mock"
    # vision is unset, so it borrows the text provider rather than failing.
    borrowed = config.role_settings(cfg, "vision")
    assert borrowed["id"] == "mock" and borrowed["role"] == "text"


def test_an_unknown_provider_in_the_settings_is_rejected():
    cfg = config.load_config()
    with pytest.raises(config.ConfigError):
        config.role_settings(config.update_config(cfg, {"roles": {"text": {"provider": "telepathy"}}}), "text")
