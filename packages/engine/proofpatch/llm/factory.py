"""Provider factory.

Cline SDK is the only provider in v0.1, so the factory simply constructs it with
the configured (or auto-discovered) Cline account settings.
"""

from __future__ import annotations

from .cline_sdk import ClineSDKProvider
from .provider import CallRecorder, LLMProvider


def build_provider(
    settings,
    recorder: CallRecorder | None = None,
) -> LLMProvider:
    return ClineSDKProvider(
        provider_id=settings.cline_provider_id,
        model_id=settings.cline_model_id or None,
        api_key=settings.cline_api_key or None,
        base_url=settings.cline_base_url or None,
        node_bin=settings.cline_node_bin or None,
        bridge_dir=settings.cline_bridge_dir or None,
        timeout_seconds=settings.cline_timeout_seconds,
        max_iterations=settings.cline_max_iterations,
        max_retries=settings.cline_max_retries,
        recorder=recorder,
    )


def provider_metadata(provider: LLMProvider) -> tuple[str, str]:
    return getattr(provider, "name", "unknown"), getattr(provider, "model", "unknown")


__all__ = ["build_provider", "provider_metadata", "ClineSDKProvider"]

