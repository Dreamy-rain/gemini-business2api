import unittest
from unittest.mock import patch

from requests import Response

from core.duckmail_client import DuckMailClient
from core.gptmail_client import GPTMailClient
from core.outbound_proxy import OutboundProxyConfig, decrypt_secret, encrypt_secret, no_proxy_matches, normalize_proxy_url


def _make_response(status_code: int, json_text: str = "") -> Response:
    res = Response()
    res.status_code = status_code
    res._content = (json_text or "").encode("utf-8")
    res.headers["Content-Type"] = "application/json; charset=utf-8"
    return res


class TestNoProxyMatches(unittest.TestCase):
    def test_exact_host(self) -> None:
        self.assertTrue(no_proxy_matches("localhost", "localhost"))
        self.assertFalse(no_proxy_matches("example.com", "localhost"))

    def test_domain_suffix(self) -> None:
        self.assertTrue(no_proxy_matches("example.com", ".example.com"))
        self.assertTrue(no_proxy_matches("api.example.com", ".example.com"))
        self.assertFalse(no_proxy_matches("api.example.com", ".other.com"))

    def test_cidr(self) -> None:
        self.assertTrue(no_proxy_matches("10.1.2.3", "10.0.0.0/8"))
        self.assertFalse(no_proxy_matches("192.168.1.1", "10.0.0.0/8"))


class TestSecretEncryption(unittest.TestCase):
    def test_encrypt_decrypt_roundtrip(self) -> None:
        token = encrypt_secret("hello", "admin-key", purpose="t")
        self.assertEqual(decrypt_secret(token, "admin-key", purpose="t"), "hello")

    def test_decrypt_invalid_returns_empty(self) -> None:
        self.assertEqual(decrypt_secret("invalid-token", "admin-key", purpose="t"), "")


class TestOutboundProxyConfig(unittest.TestCase):
    def test_to_proxy_url_with_auth(self) -> None:
        cfg = OutboundProxyConfig(
            enabled=True,
            protocol="socks5",
            host="127.0.0.1",
            port=7890,
            username="u",
            password_enc="",
        )
        cfg.password_enc = cfg.encrypt_password("p", "admin-key")
        self.assertEqual(cfg.to_proxy_url("admin-key"), "socks5://u:p@127.0.0.1:7890")

    def test_normalize_proxy_url_legacy_host_port_user_pass(self) -> None:
        self.assertEqual(
            normalize_proxy_url("42.111.48.253:7030:ebugimzj:moq3ydvtga9x"),
            "http://ebugimzj:moq3ydvtga9x@42.111.48.253:7030",
        )

    def test_normalize_proxy_url_plain_host_port(self) -> None:
        self.assertEqual(normalize_proxy_url("127.0.0.1:7890"), "http://127.0.0.1:7890")


class TestRequestsProxyFallback(unittest.TestCase):
    def test_duckmail_proxy_error_falls_back_to_direct(self) -> None:
        calls = []

        def fake_request(method: str, url: str, **kwargs):
            calls.append({"url": url, "proxies": kwargs.get("proxies")})
            if kwargs.get("proxies"):
                raise Exception("proxy failed")
            return _make_response(200, "{}")

        with patch("requests.request", side_effect=fake_request):
            client = DuckMailClient(
                base_url="https://api.duckmail.sbs",
                proxy="http://127.0.0.1:7890",
                direct_fallback=True,
            )
            res = client._request("GET", "https://api.duckmail.sbs/domains")

        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(calls), 2)
        self.assertIsNotNone(calls[0]["proxies"])
        self.assertIsNone(calls[1]["proxies"])

    def test_gptmail_407_falls_back_to_direct(self) -> None:
        calls = []

        def fake_request(method: str, url: str, **kwargs):
            calls.append({"url": url, "proxies": kwargs.get("proxies")})
            if kwargs.get("proxies"):
                return _make_response(407, "{\"success\":false}")
            return _make_response(200, "{\"success\": true, \"data\": {\"email\": \"a@b.com\"}}")

        with patch("requests.request", side_effect=fake_request):
            client = GPTMailClient(
                base_url="https://mail.chatgpt.org.uk",
                proxy="http://127.0.0.1:7890",
                direct_fallback=True,
                api_key="gpt-test",
            )
            email = client.generate_email(domain="example.com")

        self.assertEqual(email, "a@b.com")
        self.assertEqual(len(calls), 2)
        self.assertIsNotNone(calls[0]["proxies"])
        self.assertIsNone(calls[1]["proxies"])


if __name__ == "__main__":
    unittest.main()

