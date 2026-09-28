"""WhatsApp support channel -- feature-gated per channel.

See docs/13-whatsapp-channel.md for setup and configuration reference.
Public surface (imported by services/api_service/main.py):
- get_provider() -> WhatsAppProvider  (raises ChannelDisabled if not enabled)
- handle_inbound(provider, message)   (from .router)
- load_config() -> WhatsAppChannelConfig  (from .config)
"""

from services.whatsapp_channel.config import (
    ChannelDisabled,
    WhatsAppChannelConfig,
    load_config,
)
from services.whatsapp_channel.providers.base import (
    InboundMessage,
    WhatsAppProvider,
)


def get_provider() -> WhatsAppProvider:
    """Instantiate the configured provider (meta/twilio/mock). Raises
    ChannelDisabled if the module is off; raises ValueError if the config
    names a provider we don't ship."""
    cfg = load_config()
    if not cfg.enabled:
        raise ChannelDisabled("WhatsApp channel is disabled (config.enabled=false).")
    name = cfg.provider
    if name == "meta":
        from services.whatsapp_channel.providers.meta import MetaProvider
        return MetaProvider(cfg)
    if name == "twilio":
        from services.whatsapp_channel.providers.twilio import TwilioProvider
        return TwilioProvider(cfg)
    if name == "mock":
        from services.whatsapp_channel.providers.mock import MockProvider
        return MockProvider(cfg)
    raise ValueError(f"Unknown WhatsApp provider: {name!r} (expected meta/twilio/mock).")


__all__ = [
    "ChannelDisabled",
    "InboundMessage",
    "WhatsAppChannelConfig",
    "WhatsAppProvider",
    "get_provider",
    "load_config",
]
