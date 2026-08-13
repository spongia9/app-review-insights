import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from app.providers.errors import IngestionError


APP_ID_PATTERN = re.compile(r"^id(?P<app_id>[0-9]+)$", re.IGNORECASE)


@dataclass(frozen=True)
class AppStoreLocation:
    app_id: str
    storefront: str


def parse_us_app_store_url(value: str) -> AppStoreLocation:
    try:
        parsed = urlparse(value.strip())
    except (AttributeError, ValueError):
        parsed = None

    if (
        parsed is None
        or parsed.scheme != "https"
        or (parsed.hostname or "").lower() != "apps.apple.com"
    ):
        raise IngestionError(
            "INVALID_APP_STORE_URL",
            "Enter a valid HTTPS apps.apple.com U.S. App Store URL.",
            status_code=422,
        )

    segments = [unquote(segment) for segment in parsed.path.split("/") if segment]
    if len(segments) < 3 or segments[0].lower() != "us" or segments[1].lower() != "app":
        raise IngestionError(
            "INVALID_APP_STORE_URL",
            "The App Store URL must use the U.S. storefront (/us/app/...).",
            status_code=422,
        )

    app_id = None
    for segment in reversed(segments):
        match = APP_ID_PATTERN.fullmatch(segment)
        if match:
            app_id = match.group("app_id")
            break

    if app_id is None:
        raise IngestionError(
            "INVALID_APP_STORE_URL",
            "The App Store URL does not contain a valid numeric app ID.",
            status_code=422,
        )

    return AppStoreLocation(app_id=app_id, storefront="us")
