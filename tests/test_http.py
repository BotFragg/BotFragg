"""Behavior checks for http."""

from __future__ import annotations

from src.services.http import _safe_log_url

_OPTIONAL_URLS = (
    "SUPPORT_URL",
    "VOTE_URL",
    "WEBSITE_URL",
    "SHARD_LOG_WEBHOOK_URL",
)


def test_http_log_urls_remove_account_ids_credentials_and_queries() -> None:
    """Verify that HTTP log urls remove account IDs credentials and queries."""
    puuid = "123e4567-e89b-12d3-a456-426614174000"
    safe_url = _safe_log_url(
        f"https://user:password@pd.na.a.pvp.net/store/v3/storefront/{puuid}"
        "?token=secret"
    )

    assert safe_url == "https://pd.na.a.pvp.net/store/v3/storefront/[Filtered]"
    assert puuid not in safe_url
    assert "password" not in safe_url
    assert "secret" not in safe_url
