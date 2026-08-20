from __future__ import annotations

from dataclasses import dataclass
import random
import time
from typing import Any

import httpx

from mlb_hr.config import CONFIG


class ResponseTooLarge(RuntimeError):
    pass


@dataclass(slots=True)
class HttpResponse:
    status_code: int
    headers: httpx.Headers
    content: bytes
    url: str

    def json(self) -> Any:
        import json
        return json.loads(self.content.decode("utf-8"))

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class HttpClient:
    def __init__(self, user_agent: str | None = None) -> None:
        timeout = httpx.Timeout(
            connect=CONFIG.network_connect_timeout_s,
            read=CONFIG.network_read_timeout_s,
            write=CONFIG.network_write_timeout_s,
            pool=CONFIG.network_pool_timeout_s,
        )
        self.client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": user_agent or CONFIG.user_agent,
                "Accept": "application/json,text/csv;q=0.9,*/*;q=0.1",
            },
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        max_bytes: int | None = None,
    ) -> HttpResponse:
        max_size = max_bytes or CONFIG.max_response_bytes
        retryable_status = {408, 425, 429, 500, 502, 503, 504}
        last_error: Exception | None = None

        for attempt in range(CONFIG.max_retries + 1):
            try:
                with self.client.stream("GET", url, params=params, headers=headers) as response:
                    if response.status_code in retryable_status and attempt < CONFIG.max_retries:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = min(float(retry_after), 10.0)
                            except ValueError:
                                delay = CONFIG.retry_base_delay_s * (2**attempt)
                        else:
                            delay = CONFIG.retry_base_delay_s * (2**attempt)
                        time.sleep(delay + random.uniform(0, 0.15))
                        continue

                    response.raise_for_status()
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > max_size:
                            raise ResponseTooLarge(f"Response exceeded {max_size} bytes")
                        chunks.append(chunk)
                    return HttpResponse(
                        status_code=response.status_code,
                        headers=response.headers,
                        content=b"".join(chunks),
                        url=str(response.url),
                    )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError, ResponseTooLarge) as exc:
                last_error = exc
                if attempt >= CONFIG.max_retries or isinstance(exc, ResponseTooLarge):
                    break
                time.sleep(CONFIG.retry_base_delay_s * (2**attempt) + random.uniform(0, 0.15))

        if last_error:
            raise last_error
        raise RuntimeError("HTTP request failed without an exception")
