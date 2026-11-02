"""Local proxy servers only: no paid proxy, real credentials, or external API calls."""
import base64
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

import pytest

from ingestion.clients.http import SourceError, get_json
from ingestion.clients.proxy import OutboundClient
from shared.config import proxy_config


@contextmanager
def local_proxy(status=200, connections=None):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            requests.append((self.path, self.headers.get("Proxy-Authorization")))
            if connections is not None:
                connections.append(self.client_address)
            body = b'{"ok": true}'
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_round_robin_routes_actual_requests(settings):
    with local_proxy() as (a, calls_a), local_proxy() as (b, calls_b):
        settings = replace(settings, proxy_enabled=True, proxy_urls=(a, b))
        with OutboundClient(settings) as client:
            for path in ("/seoul", "/weather", "/seoul-next"):
                assert get_json(client, "http://origin.invalid" + path, source="test") == {"ok": True}
    assert [path for path, _ in calls_a] == ["http://origin.invalid/seoul", "http://origin.invalid/seoul-next"]
    assert [path for path, _ in calls_b] == ["http://origin.invalid/weather"]


def test_retry_switches_proxy(settings):
    with local_proxy(503) as (a, calls_a), local_proxy() as (b, calls_b):
        with OutboundClient(replace(settings, proxy_enabled=True, proxy_urls=(a, b))) as client:
            assert get_json(client, "http://origin.invalid/", source="test", attempts=2, backoff=0)["ok"]
    assert len(calls_a) == len(calls_b) == 1


def test_proxy_auth_and_single_gateway(settings):
    with local_proxy() as (url, calls):
        proxy = url.replace("http://", "http://test-user:test%40password@")
        with OutboundClient(replace(settings, proxy_enabled=True, proxy_urls=(proxy,))) as client:
            for _ in range(2):
                get_json(client, "http://origin.invalid/", source="test")
    expected = "Basic " + base64.b64encode(b"test-user:test@password").decode()
    assert len(calls) == 2 and all(auth == expected for _, auth in calls)


def test_each_gateway_request_opens_a_new_connection(settings):
    connections = []
    with local_proxy(connections=connections) as (url, _):
        with OutboundClient(replace(settings, proxy_enabled=True, proxy_urls=(url,))) as client:
            for _ in range(3):
                get_json(client, "http://origin.invalid/", source="test")
    assert len(connections) == len(set(connections)) == 3


def test_failed_proxy_has_no_direct_fallback(settings):
    with local_proxy(502) as (url, calls):
        with OutboundClient(replace(settings, proxy_enabled=True, proxy_urls=(url,))) as client:
            # origin.invalid cannot resolve; every attempt must still reach the configured proxy.
            with pytest.raises(SourceError, match="HTTP 502"):
                get_json(client, "http://origin.invalid/", source="test", attempts=3, backoff=0)
    assert len(calls) == 3


def test_proxy_auth_error_does_not_expose_credentials(settings):
    with local_proxy(407) as (url, calls):
        url = url.replace("http://", "http://test-user:private-test-password@")
        with OutboundClient(replace(settings, proxy_enabled=True, proxy_urls=(url,))) as client:
            with pytest.raises(SourceError, match="HTTP 407") as error:
                get_json(client, "http://origin.invalid/", source="test", attempts=3, backoff=0)
    assert len(calls) == 1
    assert "private-test-password" not in str(error.value)
    assert "private-test-password" not in repr(settings)


@pytest.mark.parametrize("value", ['["http://user:secret@host:bad"]', '["socks5://host:123"]',
    '["http://host:123/path"]', '["http://host:123?secret=value"]', '[null]', '{}', 'invalid'])
def test_invalid_proxy_configuration_is_redacted(monkeypatch, value):
    monkeypatch.setenv("OUTBOUND_PROXY_URLS", value)
    with pytest.raises(ValueError) as error:
        proxy_config()
    assert "secret" not in str(error.value)
    assert "value" not in str(error.value)


def test_enabled_proxy_cannot_have_empty_pool(monkeypatch):
    monkeypatch.setenv("OUTBOUND_PROXY_ENABLED", "true")
    monkeypatch.setenv("OUTBOUND_PROXY_URLS", "[]")
    with pytest.raises(ValueError, match="at least one URL"):
        proxy_config()


def test_enabled_proxy_cannot_fall_back_when_constructed_without_urls(settings):
    with pytest.raises(ValueError, match="at least one configured proxy"):
        with OutboundClient(replace(settings, proxy_enabled=True, proxy_urls=())):
            pytest.fail("must reject configuration")


def test_proxy_config_accepts_one_gateway_and_deduplicates(monkeypatch):
    monkeypatch.setenv("OUTBOUND_PROXY_ENABLED", "true")
    monkeypatch.setenv("OUTBOUND_PROXY_URLS", '["http://user:encoded%40password@host:8080", "http://user:encoded%40password@host:8080"]')
    enabled, urls = proxy_config()
    assert enabled and len(urls) == 1


def test_disabled_proxy_uses_direct_connection(settings, monkeypatch):
    # A local origin server acts as a direct target, while the unused proxy is unreachable.
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("ALL_PROXY", "http://127.0.0.1:1")
    with local_proxy() as (url, calls):
        with OutboundClient(replace(settings, proxy_enabled=False, proxy_urls=("http://127.0.0.1:1",))) as client:
            assert get_json(client, url + "/direct", source="test")["ok"]
    assert calls == [("/direct", None)]
