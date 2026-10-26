"""Small JSON client; secrets and server response bodies never enter exceptions."""

import json
import time
import urllib.error
import urllib.request


class AutomationError(Exception):
    """A safe, actionable error suitable for CI output."""


class ApiError(AutomationError):
    def __init__(self, status, method, path, data=None):
        self.status = status
        self.data = data if isinstance(data, dict) else {}
        super().__init__(f"API {method} {path.split('?')[0]} returned HTTP {status}")


class AmbiguousWrite(AutomationError):
    def __init__(self, data=None):
        self.data = data if isinstance(data, dict) else {}
        super().__init__("Write outcome unknown; reconcile by record key before retrying")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never send credentials to a redirected host.
        return None


class JsonClient:
    def __init__(self, base, token, *, headers=None, opener=None, sleep=time.sleep):
        self.base = base.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "AI-TOP-100-evidence/1",
            **(headers or {}),
        }
        self.opener = opener or urllib.request.build_opener(NoRedirect())
        self.sleep = sleep

    def request(self, method, path, body=None, *, idempotent=False):
        if not path.startswith("/") or path.startswith("//"):
            raise AutomationError("API path must be relative to the configured host")
        payload = None if body is None else json.dumps(body, ensure_ascii=False).encode()
        for attempt in range(4):
            request = urllib.request.Request(
                self.base + path, data=payload, method=method, headers=self.headers
            )
            try:
                with self.opener.open(request, timeout=30) as response:
                    raw = response.read(5_000_001)
                    if len(raw) > 5_000_000:
                        raise AutomationError("API response exceeds safety limit")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as error:
                try:
                    data = json.loads(error.read(16384))
                except (ValueError, UnicodeError):
                    data = {}
                if not isinstance(data, dict):
                    data = {}
                if method not in ("GET", "HEAD") and not idempotent and error.code >= 500 and error.code != 529:
                    raise AmbiguousWrite(data) from None
                reason = data.get("additional_data", {}).get("rate_limit_reason")
                retryable = error.code in (429, 529) and reason != "public_api_request_blocked"
                retryable |= (method == "GET" or idempotent) and error.code in (500, 502, 503, 504)
                if not retryable or attempt == 3:
                    raise ApiError(error.code, method, path, data) from None
                try:
                    delay = float(error.headers.get("Retry-After", 2 ** attempt))
                except ValueError:
                    delay = float(2 ** attempt)
                if delay < 0 or delay > 60:
                    raise AutomationError("API retry delay exceeds 60 seconds; rerun later") from None
                self.sleep(delay)
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                if method not in ("GET", "HEAD") and not idempotent:
                    raise AmbiguousWrite() from None
                if attempt == 3:
                    raise AutomationError("API network request failed after bounded retries") from None
                self.sleep(2 ** attempt)
            except (ValueError, UnicodeError):
                if method not in ("GET", "HEAD") and not idempotent:
                    raise AmbiguousWrite() from None
                raise AutomationError("API returned invalid JSON") from None
        raise AutomationError("API retries exhausted")
