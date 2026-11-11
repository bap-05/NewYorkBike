"""Bounded network retries. Errors deliberately exclude URLs, bodies and secrets."""
import re
import time
import httpx


class SourceError(RuntimeError):
    pass


def get_json(client, url, *, source, attempts=3, backoff=1, params=None):
    bronze = getattr(client, "bronze", None)
    for attempt in range(attempts):
        try:
            response = client.get(url, params=params)
            if bronze is not None:
                bronze.record_response(response, source=source, request_attempt=attempt + 1, url=url, params=params)
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 < attempts:
                    time.sleep(backoff * 2 ** attempt)
                    continue
            if response.status_code != 200:
                raise SourceError(f"{source}: HTTP {response.status_code}")
            payload = response.json()
            if not isinstance(payload, dict):
                raise SourceError(f"{source}: expected JSON object")
            return payload
        except httpx.RequestError as exc:
            if bronze is not None:
                bronze.record_failure(source=source, request_attempt=attempt + 1,
                                      error_type=type(exc).__name__, url=url, params=params)
            if attempt + 1 == attempts:
                if isinstance(exc, httpx.ProxyError):
                    # HTTPS CONNECT failures arrive as exceptions, not Responses.
                    # Only expose the recognized status, never raw exception text.
                    if re.match(r'^407(?:\s|$)', str(exc)):
                        raise SourceError(f"{source}: proxy HTTP 407 after {attempts} attempts; "
                            "proxy authentication rejected; check credentials and provider account") from None
                    raise SourceError(f"{source}: proxy connection failed after {attempts} attempts; "
                        "check proxy credentials, provider limits and gateway availability") from None
                # Exception messages may contain proxy credentials. Fixed error
                # categories distinguish timeouts/connections without leaking them.
                category = (
                    "connection timeout" if isinstance(exc, httpx.ConnectTimeout) else
                    "response timeout" if isinstance(exc, httpx.ReadTimeout) else
                    "network timeout" if isinstance(exc, httpx.TimeoutException) else
                    "connection failed" if isinstance(exc, httpx.ConnectError) else
                    "response read failed" if isinstance(exc, httpx.ReadError) else
                    "invalid remote protocol" if isinstance(exc, httpx.RemoteProtocolError) else
                    "network request failed"
                )
                raise SourceError(f"{source}: {category} after {attempts} attempts") from None
            time.sleep(backoff * 2 ** attempt)
        except ValueError:
            raise SourceError(f"{source}: invalid JSON response") from None
    raise SourceError(f"{source}: retries exhausted")
