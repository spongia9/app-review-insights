from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from app.providers.app_store_url import AppStoreLocation, parse_us_app_store_url
from app.providers.base import ProviderBatch, ReviewCandidate, ReviewProvider
from app.providers.errors import IngestionError


class AppStoreProvider(ReviewProvider):
    source = "apple_customer_reviews_rss"
    storefront = "us"
    feed_template = (
        "https://itunes.apple.com/us/rss/customerreviews/"
        "page={page}/id={app_id}/sortby=mostrecent/json"
    )

    def __init__(
        self,
        app_store_url: str,
        *,
        max_pages: int,
        max_review_rows: int,
        timeout_seconds: float,
        client: Optional[httpx.Client] = None,
    ) -> None:
        self.location: AppStoreLocation = parse_us_app_store_url(app_store_url)
        self.max_pages = max_pages
        self.max_review_rows = max_review_rows
        self.timeout_seconds = timeout_seconds
        self.client = client

    def load(self) -> ProviderBatch:
        collected: List[ReviewCandidate] = []
        limitations = [
            "Apple's public customer-review RSS feed is storefront-specific but undocumented as a stable API.",
            f"Results are limited to the most recent reviews available in at most {self.max_pages} feed pages.",
            "Feed availability, pagination, ordering, and schema may change without notice.",
        ]
        owns_client = self.client is None
        client = self.client or httpx.Client(
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"Accept": "application/json", "User-Agent": "AppReviewInsights/0.2"},
        )

        try:
            for page in range(1, self.max_pages + 1):
                feed_url = self.feed_template.format(page=page, app_id=self.location.app_id)
                try:
                    response = client.get(feed_url)
                    response.raise_for_status()
                    payload = response.json()
                except (httpx.HTTPError, ValueError) as error:
                    raise IngestionError(
                        "APP_STORE_COLLECTION_FAILED",
                        "Unable to collect U.S. App Store reviews from Apple's customer-review feed.",
                        status_code=502,
                        details={"app_id": self.location.app_id, "storefront": self.storefront},
                    ) from error

                entries = self._review_entries(payload)
                if not entries:
                    break
                for entry in entries:
                    if len(collected) >= self.max_review_rows:
                        limitations.append(
                            f"Collection stopped at the configured {self.max_review_rows}-review limit."
                        )
                        break
                    collected.append(self._candidate(entry))
                if len(collected) >= self.max_review_rows or len(entries) < 50:
                    break
        finally:
            if owns_client:
                client.close()

        if not collected:
            raise IngestionError(
                "NO_VALID_REVIEWS",
                "The U.S. App Store feed returned no review records for this app.",
                status_code=422,
                details={"app_id": self.location.app_id, "storefront": self.storefront},
            )

        return ProviderBatch(
            source=self.source,
            collection_time=datetime.now(timezone.utc),
            candidates=collected,
            raw_review_count=len(collected),
            storefront=self.storefront,
            app_id=self.location.app_id,
            source_limitations=limitations,
            is_live_collection=True,
            storefront_verified=True,
        )

    @staticmethod
    def _review_entries(payload: Any) -> List[Dict[str, Any]]:
        if not isinstance(payload, dict):
            raise IngestionError(
                "APP_STORE_COLLECTION_FAILED",
                "Apple's customer-review feed returned an unexpected document shape.",
                status_code=502,
            )
        feed = payload.get("feed")
        if not isinstance(feed, dict):
            raise IngestionError(
                "APP_STORE_COLLECTION_FAILED",
                "Apple's customer-review feed did not include a feed object.",
                status_code=502,
            )
        entries = feed.get("entry", [])
        if not isinstance(entries, list):
            raise IngestionError(
                "APP_STORE_COLLECTION_FAILED",
                "Apple's customer-review feed entries were not a list.",
                status_code=502,
            )
        return [entry for entry in entries if isinstance(entry, dict) and "im:rating" in entry]

    def _candidate(self, entry: Dict[str, Any]) -> ReviewCandidate:
        return ReviewCandidate(
            source=self.source,
            raw_data=entry,
            source_review_id=self._label(entry.get("id")),
            app_id=self.location.app_id,
            author=self._label((entry.get("author") or {}).get("name")),
            rating=self._label(entry.get("im:rating")),
            title=self._label(entry.get("title")),
            text=self._label(entry.get("content")),
            version=self._label(entry.get("im:version")),
            language=None,
            created_at=self._label(entry.get("updated")),
            storefront=self.storefront,
        )

    @staticmethod
    def _label(value: Any) -> Optional[Any]:
        if isinstance(value, dict):
            return value.get("label")
        return value
