import json
import unittest
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from unittest.mock import patch

from requests import Response

from core.gptmail_client import GPTMailClient


def _make_response(status_code: int, payload: Optional[Dict[str, Any]] = None) -> Response:
    res = Response()
    res.status_code = status_code
    if payload is None:
        res._content = b""
    else:
        res._content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        res.headers["Content-Type"] = "application/json; charset=utf-8"
    return res


class TestGPTMailClient(unittest.TestCase):
    def test_generate_email_success_sets_email(self) -> None:
        captured = {}

        def fake_request(method: str, url: str, **kwargs):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = kwargs.get("headers") or {}
            return _make_response(
                200,
                {"success": True, "data": {"email": "myname@example.com"}, "error": ""},
            )

        with patch("requests.request", side_effect=fake_request):
            client = GPTMailClient(base_url="https://mail.chatgpt.org.uk", api_key="gpt-test")
            email = client.generate_email(domain="example.com")

        self.assertEqual(email, "myname@example.com")
        self.assertEqual(client.email, "myname@example.com")
        self.assertEqual(captured["headers"].get("X-API-Key"), "gpt-test")
        self.assertEqual(captured["method"], "POST")
        self.assertIn("/api/generate-email", captured["url"])

    def test_poll_for_code_uses_detail_when_list_has_no_code(self) -> None:
        now = datetime.now().replace(microsecond=0)
        since_time = now - timedelta(minutes=1)

        def fake_request(method: str, url: str, **kwargs):
            if url.endswith("/api/emails"):
                return _make_response(
                    200,
                    {
                        "success": True,
                        "data": {
                            "emails": [
                                {
                                    "id": "123",
                                    "timestamp": int(now.timestamp()),
                                    "content": "no code here",
                                    "html_content": "",
                                }
                            ],
                            "count": 1,
                        },
                        "error": "",
                    },
                )
            if url.endswith("/api/email/123"):
                return _make_response(
                    200,
                    {
                        "success": True,
                        "data": {
                            "id": "123",
                            "timestamp": int(now.timestamp()),
                            "raw_content": "Your verification code: ABC123",
                        },
                        "error": "",
                    },
                )
            raise AssertionError(f"unexpected request: {method} {url}")

        with patch("requests.request", side_effect=fake_request):
            client = GPTMailClient(base_url="https://mail.chatgpt.org.uk", api_key="gpt-test")
            client.set_credentials("test@example.com")
            code = client.poll_for_code(timeout=4, interval=2, since_time=since_time)

        self.assertEqual(code, "ABC123")


if __name__ == "__main__":
    unittest.main()

