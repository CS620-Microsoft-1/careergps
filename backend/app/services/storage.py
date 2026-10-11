"""Private file storage for résumés (Supabase Storage)."""
from typing import Protocol
from urllib.parse import quote

import httpx2

TIMEOUT_SECONDS = 30


class StorageError(Exception):
    """The storage service failed or is unreachable."""


class FileStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class SupabaseStorage:
    """Talks to Supabase Storage's REST API with the secret (service-role) key. Backend only."""

    def __init__(self, supabase_url: str, secret_key: str, bucket: str) -> None:
        self._base = f"{supabase_url.rstrip('/')}/storage/v1/object/{quote(bucket)}"
        self._headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}

    def _url(self, key: str) -> str:
        return f"{self._base}/{quote(key)}"

    def _request(self, method: str, key: str, extra_headers: dict[str, str] | None = None, **kwargs) -> httpx2.Response:
        try:
            response = httpx2.request(
                method,
                self._url(key),
                headers={**self._headers, **(extra_headers or {})},
                timeout=TIMEOUT_SECONDS,
                **kwargs,
            )
            response.raise_for_status()
        except httpx2.HTTPError as error:
            # Status only: the response body could echo the request.
            raise StorageError(f"{method} storage object failed: {type(error).__name__}") from error
        return response

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._request("POST", key, extra_headers={"Content-Type": content_type}, content=data)

    def get(self, key: str) -> bytes:
        return self._request("GET", key).content

    def delete(self, key: str) -> None:
        self._request("DELETE", key)
