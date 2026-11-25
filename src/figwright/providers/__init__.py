"""Model providers: one small client per API dialect."""

from __future__ import annotations

from ..config import ConfigError, load_config, role_settings
from .base import ChatResult, Provider, ProviderError

__all__ = ["ChatResult", "Provider", "ProviderError", "make_provider", "provider_for_role"]


def make_provider(settings: dict) -> Provider:
    """Build the client for a provider's effective settings (see ``config.provider_settings``)."""
    kind = settings.get("type")
    if kind == "mock":
        from .mock import MockProvider

        return MockProvider(settings)
    if settings.get("needs_key") and not settings.get("api_key"):
        raise ProviderError("config", f"No API key is set for {settings.get('id')}. Add it in Settings.")
    if kind == "anthropic":
        from .anthropic_provider import AnthropicProvider

        return AnthropicProvider(settings)
    if kind == "gemini":
        from .gemini import GeminiProvider

        return GeminiProvider(settings)
    if kind == "openai":
        if not settings.get("base_url"):
            raise ProviderError("config", f"No API address is set for {settings.get('id')}. Add it in Settings.")
        from .openai_compat import OpenAICompatProvider

        return OpenAICompatProvider(settings)
    raise ProviderError("config", f"Unknown provider type {kind!r}.")


def provider_for_role(role: str, cfg: dict | None = None) -> Provider:
    try:
        settings = role_settings(cfg if cfg is not None else load_config(), role)
    except ConfigError as exc:
        raise ProviderError("config", str(exc)) from exc
    if settings["type"] != "mock" and not settings.get("model"):
        raise ProviderError("config", f"No model is chosen for {settings['id']}. Pick one in Settings (the 'list models' button shows what the provider offers).")
    return make_provider(settings)
