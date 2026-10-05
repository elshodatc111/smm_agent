from django.conf import settings

from .base import Connector, Platform


def get_connector(account) -> Connector:
    """Hisob uchun connector. USE_FAKES=1 bo'lsa Fake qaytadi (kalitsiz demo/test)."""
    if getattr(settings, "USE_FAKES", False):
        from .fake import FakeConnector
        return FakeConnector(account)
    p = Platform(account.platform)
    if p == Platform.TELEGRAM:
        from .telegram import TelegramChannelConnector
        return TelegramChannelConnector(account)
    if p == Platform.INSTAGRAM:
        from .instagram import InstagramConnector
        return InstagramConnector(account)
    from .youtube import YouTubeConnector
    return YouTubeConnector(account)
