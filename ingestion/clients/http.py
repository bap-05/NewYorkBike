"""Bounded network retries. Errors deliberately exclude URLs, bodies and secrets."""
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
                raise SourceError(f"{source}: network request failed after {attempts} attempts") from None
            time.sleep(backoff * 2 ** attempt)
        except ValueError:
            raise SourceError(f"{source}: invalid JSON response") from None
    raise SourceError(f"{source}: retries exhausted")
