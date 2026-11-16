"""Round-robin outbound routing shared by both source clients; no direct fallback."""
from contextlib import ExitStack
from itertools import cycle

import httpx


class OutboundClient:
    """Rotate proxy routes per request; fresh proxy connections allow gateway rotation."""

    def __init__(self, settings):
        self.settings = settings
        self._stack = None
        self._clients = None

    def __enter__(self):
        if self._stack is not None:
            raise RuntimeError("OutboundClient is already open")
        settings = self.settings
        if settings.proxy_enabled and not settings.proxy_urls:
            raise ValueError("Proxy mode requires at least one configured proxy")
        stack = ExitStack()
        try:
            routes = settings.proxy_urls if settings.proxy_enabled else (None,)
            clients = []
            for proxy in routes:
                clients.append(stack.enter_context(httpx.Client(
                    proxy=proxy, timeout=httpx.Timeout(settings.timeout_seconds),
                    limits=httpx.Limits(max_keepalive_connections=0) if proxy else httpx.Limits(),
                    follow_redirects=False, trust_env=False)))
        except (ValueError, httpx.InvalidURL):
            stack.close()
            raise ValueError("Unable to configure outbound HTTP clients; check proxy URLs") from None
        except BaseException:
            stack.close()
            raise
        self._stack = stack
        self._clients = cycle(clients)
        return self

    def get(self, url, *, params=None):
        if self._clients is None:
            raise RuntimeError("Use OutboundClient as a context manager")
        # get_json calls get again for each retry, advancing to the next proxy.
        return next(self._clients).get(url, params=params)

    def __exit__(self, *exc):
        try:
            return self._stack.__exit__(*exc)
        finally:
            self._clients = None
            self._stack = None
