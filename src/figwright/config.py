"""Settings: where things live, which model providers are configured.

Everything is local. Settings are one JSON file (``~/.figwright/config.json``,
mode 0600); API keys never leave the machine except in requests to the
provider they belong to, are never logged, and are only ever shown masked.
"""

from __future__ import annotations

import ipaddress
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROLES = ("text", "vision", "image")

# The provider catalogue. "type" selects the client implementation; everything
# marked "openai" speaks the OpenAI-compatible chat/completions dialect.
# Model ids are intentionally not baked in (they go stale): the settings page
# has a "list models" button that asks the provider what it currently offers.
PRESETS: dict[str, dict[str, Any]] = {
    "mock": {"label": {"zh": "离线演示（无需密钥）", "en": "Offline demo (no key needed)"}, "type": "mock", "base_url": "", "env": "", "needs_key": False, "roles": ["text", "vision", "image"]},
    "anthropic": {"label": {"zh": "Anthropic Claude", "en": "Anthropic Claude"}, "type": "anthropic", "base_url": "", "env": "ANTHROPIC_API_KEY", "needs_key": True, "roles": ["text", "vision"], "default_model": "claude-opus-5-5"},
    "openai": {"label": {"zh": "OpenAI", "en": "OpenAI"}, "type": "openai", "base_url": "https://api.openai.com/v1", "env": "OPENAI_API_KEY", "needs_key": True, "roles": ["text", "vision", "image"]},
    "gemini": {"label": {"zh": "Google Gemini", "en": "Google Gemini"}, "type": "gemini", "base_url": "https://generativelanguage.googleapis.com/v1beta", "env": "GEMINI_API_KEY", "needs_key": True, "roles": ["text", "vision", "image"]},
    "deepseek": {"label": {"zh": "DeepSeek", "en": "DeepSeek"}, "type": "openai", "base_url": "https://api.deepseek.com/v1", "env": "DEEPSEEK_API_KEY", "needs_key": True, "roles": ["text"]},
    "dashscope": {"label": {"zh": "阿里云百炼（通义千问）", "en": "Alibaba DashScope (Qwen)"}, "type": "openai", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "env": "DASHSCOPE_API_KEY", "needs_key": True, "roles": ["text", "vision"]},
    "moonshot": {"label": {"zh": "月之暗面 Kimi", "en": "Moonshot Kimi"}, "type": "openai", "base_url": "https://api.moonshot.cn/v1", "env": "MOONSHOT_API_KEY", "needs_key": True, "roles": ["text", "vision"]},
    "zhipu": {"label": {"zh": "智谱 GLM", "en": "Zhipu GLM"}, "type": "openai", "base_url": "https://open.bigmodel.cn/api/paas/v4", "env": "ZHIPU_API_KEY", "needs_key": True, "roles": ["text", "vision", "image"]},
    "siliconflow": {"label": {"zh": "硅基流动", "en": "SiliconFlow"}, "type": "openai", "base_url": "https://api.siliconflow.cn/v1", "env": "SILICONFLOW_API_KEY", "needs_key": True, "roles": ["text", "vision", "image"]},
    "tokenhub": {"label": {"zh": "腾讯 TokenHub（混元）", "en": "Tencent TokenHub (Hunyuan)"}, "type": "openai", "base_url": "https://tokenhub.tencentmaas.com/v1", "env": "TOKENHUB_API_KEY", "needs_key": True, "roles": ["text", "vision"]},
    "qianfan": {"label": {"zh": "百度千帆（文心）", "en": "Baidu Qianfan (ERNIE)"}, "type": "openai", "base_url": "https://qianfan.baidubce.com/v2", "env": "QIANFAN_API_KEY", "needs_key": True, "roles": ["text", "vision"]},
    "openrouter": {"label": {"zh": "OpenRouter", "en": "OpenRouter"}, "type": "openai", "base_url": "https://openrouter.ai/api/v1", "env": "OPENROUTER_API_KEY", "needs_key": True, "roles": ["text", "vision", "image"]},
    "xai": {"label": {"zh": "xAI Grok", "en": "xAI Grok"}, "type": "openai", "base_url": "https://api.x.ai/v1", "env": "XAI_API_KEY", "needs_key": True, "roles": ["text", "vision", "image"]},
    "mistral": {"label": {"zh": "Mistral", "en": "Mistral"}, "type": "openai", "base_url": "https://api.mistral.ai/v1", "env": "MISTRAL_API_KEY", "needs_key": True, "roles": ["text", "vision"]},
    "groq": {"label": {"zh": "Groq", "en": "Groq"}, "type": "openai", "base_url": "https://api.groq.com/openai/v1", "env": "GROQ_API_KEY", "needs_key": True, "roles": ["text", "vision"]},
    "ollama": {"label": {"zh": "Ollama（本机）", "en": "Ollama (local)"}, "type": "openai", "base_url": "http://localhost:11434/v1", "env": "", "needs_key": False, "roles": ["text", "vision"]},
    "lmstudio": {"label": {"zh": "LM Studio（本机）", "en": "LM Studio (local)"}, "type": "openai", "base_url": "http://localhost:1234/v1", "env": "", "needs_key": False, "roles": ["text", "vision"]},
    "custom": {"label": {"zh": "自定义（OpenAI 兼容）", "en": "Custom (OpenAI-compatible)"}, "type": "openai", "base_url": "", "env": "FIGWRIGHT_CUSTOM_API_KEY", "needs_key": False, "roles": ["text", "vision", "image"]},
}

DEFAULT_CONFIG: dict[str, Any] = {
    "providers": {},
    "roles": {"text": {"provider": "mock", "model": ""}, "vision": {"provider": "", "model": ""}, "image": {"provider": "mock", "model": ""}},
    "lang": "zh",
    "house_style": None,
}


class ConfigError(ValueError):
    """A setting is unusable; the message is safe to show to the user."""


def home() -> Path:
    return Path(os.environ.get("FIGWRIGHT_HOME") or (Path.home() / ".figwright"))


def config_path() -> Path:
    return home() / "config.json"


def projects_dir() -> Path:
    return home() / "projects"


def mask_key(key: str | None) -> str:
    """A hint that identifies a key without revealing it."""
    if not key:
        return ""
    k = str(key)
    return "•" * 6 if len(k) < 12 else f"{k[:3]}…{k[-4:]}"


def _is_local(host: str) -> bool:
    if host in ("localhost", "host.docker.internal") or host.endswith(".localhost") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def check_base_url(url: str) -> str:
    """Validate a provider endpoint. Plain http is only allowed for this machine and the local network."""
    u = (url or "").strip().rstrip("/")
    if not u:
        return ""
    parsed = urlparse(u)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ConfigError("The API address must start with https:// (or http:// for a server on this computer or local network).")
    if parsed.username or parsed.password:
        raise ConfigError("Do not put credentials in the API address; use the key field.")
    if parsed.scheme == "http" and not _is_local(parsed.hostname):
        raise ConfigError("Plain http:// would send your API key unencrypted. Use https://, or http:// only for a local server.")
    return u


def load_config() -> dict:
    cfg = deepcopy(DEFAULT_CONFIG)
    path = config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if isinstance(data, dict):
            if isinstance(data.get("providers"), dict):
                cfg["providers"] = {str(k): v for k, v in data["providers"].items() if isinstance(v, dict) and k in PRESETS}
            if isinstance(data.get("roles"), dict):
                for role in ROLES:
                    r = data["roles"].get(role)
                    if isinstance(r, dict):
                        cfg["roles"][role] = {"provider": str(r.get("provider") or ""), "model": str(r.get("model") or "")}
            if data.get("lang") in ("zh", "en"):
                cfg["lang"] = data["lang"]
            if isinstance(data.get("house_style"), dict):
                cfg["house_style"] = data["house_style"]
    # Environment overrides (handy for servers, CI and the MCP server).
    for role in ROLES:
        p = os.environ.get(f"FIGWRIGHT_{role.upper()}_PROVIDER")
        m = os.environ.get(f"FIGWRIGHT_{role.upper()}_MODEL")
        if p and p in PRESETS:
            cfg["roles"][role]["provider"] = p
        if m:
            cfg["roles"][role]["model"] = m
    return cfg


def save_config(cfg: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path.parent, 0o700)
    except OSError:
        pass
    data = {"providers": cfg.get("providers", {}), "roles": cfg.get("roles", {}), "lang": cfg.get("lang", "zh"), "house_style": cfg.get("house_style")}
    fd, tmp = tempfile.mkstemp(prefix="config-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def provider_settings(cfg: dict, provider_id: str) -> dict:
    """Effective settings of one provider: preset, saved overrides, environment key."""
    if provider_id not in PRESETS:
        raise ConfigError(f"Unknown provider {provider_id!r}.")
    preset = PRESETS[provider_id]
    saved = cfg.get("providers", {}).get(provider_id, {})
    key = saved.get("api_key") or (os.environ.get(preset["env"]) if preset.get("env") else "") or ""
    base = saved.get("base_url") or preset.get("base_url") or ""
    if preset["type"] == "anthropic" and not saved.get("base_url"):
        base = os.environ.get("ANTHROPIC_BASE_URL", "")
    return {
        "id": provider_id,
        "type": preset["type"],
        "base_url": base,
        "api_key": key,
        "key_from_env": bool(key) and not saved.get("api_key"),
        "needs_key": preset.get("needs_key", True),
        "default_model": preset.get("default_model", ""),
    }


def role_settings(cfg: dict, role: str) -> dict:
    """Provider + model for a role. ``vision`` falls back to ``text``; ``image`` has no fallback."""
    r = cfg.get("roles", {}).get(role) or {}
    pid, model = r.get("provider") or "", r.get("model") or ""
    if not pid and role == "vision":
        return role_settings(cfg, "text")
    if not pid:
        raise ConfigError("No image model is configured. Open Settings and choose a provider for images." if role == "image" else "No model is configured. Open Settings and choose a provider.")
    s = provider_settings(cfg, pid)
    s["model"] = model or s["default_model"]
    s["role"] = role
    return s


def public_config(cfg: dict) -> dict:
    """The configuration as shown to the browser: keys replaced by a masked hint."""
    providers = []
    for pid, preset in PRESETS.items():
        s = provider_settings(cfg, pid)
        saved = cfg.get("providers", {}).get(pid, {})
        providers.append(
            {
                "id": pid,
                "label": preset["label"],
                "type": preset["type"],
                "base_url": s["base_url"],
                "default_base_url": preset.get("base_url", ""),
                "base_url_overridden": bool(saved.get("base_url")),
                "needs_key": preset.get("needs_key", True),
                "key_set": bool(s["api_key"]),
                "key_hint": mask_key(s["api_key"]),
                "key_from_env": s["key_from_env"],
                "env": preset.get("env", ""),
                "roles": preset.get("roles", []),
                "default_model": preset.get("default_model", ""),
            }
        )
    return {"providers": providers, "roles": deepcopy(cfg.get("roles", {})), "lang": cfg.get("lang", "zh"), "house_style": cfg.get("house_style"), "config_path": str(config_path())}


def update_config(cfg: dict, patch: dict) -> dict:
    """Apply a settings change coming from the UI. Returns the new configuration (already saved)."""
    out = deepcopy(cfg)
    for pid, p in (patch.get("providers") or {}).items():
        if pid not in PRESETS or not isinstance(p, dict):
            continue
        cur = dict(out["providers"].get(pid, {}))
        if "base_url" in p:
            url = check_base_url(str(p.get("base_url") or ""))
            if url and url != PRESETS[pid].get("base_url", "").rstrip("/"):
                cur["base_url"] = url
            else:
                cur.pop("base_url", None)
        if p.get("clear_key"):
            cur.pop("api_key", None)
        elif isinstance(p.get("api_key"), str) and p["api_key"].strip():
            key = p["api_key"].strip()
            if any(ch in key for ch in "\r\n\t ") or "•" in key or "…" in key:
                raise ConfigError("That does not look like an API key (it contains spaces or mask characters).")
            cur["api_key"] = key
        if cur:
            out["providers"][pid] = cur
        else:
            out["providers"].pop(pid, None)
    for role, r in (patch.get("roles") or {}).items():
        if role in ROLES and isinstance(r, dict):
            pid = str(r.get("provider") or "")
            if pid and pid not in PRESETS:
                raise ConfigError(f"Unknown provider {pid!r}.")
            out["roles"][role] = {"provider": pid, "model": str(r.get("model") or "").strip()[:200]}
    if patch.get("lang") in ("zh", "en"):
        out["lang"] = patch["lang"]
    if "house_style" in patch:
        hs = patch["house_style"]
        out["house_style"] = hs if isinstance(hs, dict) else None
    save_config(out)
    return out
