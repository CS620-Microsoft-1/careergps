from __future__ import annotations

from typing import Any, Protocol

import httpx2

from app.schemas.market import NormalizedPosting

USER_AGENT = "CareerGPS/0.1 (job market research; +https://github.com/CS620-Microsoft-1/careergps)"
REQUEST_TIMEOUT_SECONDS = 30.0

# Country names that Ashby returns in postal addresses. Two-letter codes pass through unchanged.
_COUNTRY_CODES = {
    "united states": "US",
    "united states of america": "US",
    "usa": "US",
    "canada": "CA",
    "mexico": "MX",
    "brazil": "BR",
    "united kingdom": "GB",
    "ireland": "IE",
    "germany": "DE",
    "france": "FR",
    "netherlands": "NL",
    "spain": "ES",
    "switzerland": "CH",
    "poland": "PL",
    "india": "IN",
    "singapore": "SG",
    "japan": "JP",
    "south korea": "KR",
    "australia": "AU",
}


class BoardNotFoundError(LookupError):
    """The job board slug does not exist on this source."""


class BoardFetchError(RuntimeError):
    """The job board could not be fetched or returned an unexpected response."""


class PostingSourceAdapter(Protocol):
    source: str

    def fetch(self, slug: str) -> list[NormalizedPosting]: ...


def create_http_client(transport: httpx2.BaseTransport | None = None) -> httpx2.Client:
    return httpx2.Client(
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
        transport=transport,
    )


def get_json(client: httpx2.Client, url: str, params: dict[str, str] | None = None) -> Any:
    try:
        response = client.get(url, params=params)
    except httpx2.RequestError as error:
        raise BoardFetchError(f"Request to {url} failed ({type(error).__name__}).") from error
    if response.status_code == 404:
        raise BoardNotFoundError(url)
    if response.status_code != 200:
        raise BoardFetchError(f"{url} returned HTTP {response.status_code}.")
    try:
        return response.json()
    except ValueError as error:
        raise BoardFetchError(f"{url} returned invalid JSON.") from error


def country_code(value: str | None) -> str | None:
    if not value or not value.strip():
        return None
    cleaned = value.strip()
    if len(cleaned) == 2 and cleaned.isalpha():
        return cleaned.upper()
    return _COUNTRY_CODES.get(cleaned.lower())


def clean(value: Any) -> str | None:
    """Return a stripped string, or None for missing and blank values."""
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
