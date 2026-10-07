"""Offline tests with simulated registry responses. Run: python test_shield.py"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import shield


def iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat().replace("+00:00", "Z")


class Resp:
    def __init__(self, code, data=None):
        self.status_code, self._d = code, data or {}
    def json(self): return self._d
    def raise_for_status(self): pass


def fake_get(url, timeout=0):
    if "pypi.org" in url:
        name = url.split("/pypi/")[1].split("/")[0]
        if name == "requests":
            return Resp(200, {"info": {"project_urls": {"Source": "https://github.com/psf/requests"}, "home_page": ""},
                              "releases": {f"2.{i}": [{"upload_time_iso_8601": iso(3000 - i * 50)}] for i in range(20)}})
        if name == "sketchy-new-pkg":
            return Resp(200, {"info": {"project_urls": None, "home_page": ""},
                              "releases": {"0.1": [{"upload_time_iso_8601": iso(3)}]}})
        if name == "pdf-reader-pro":  # exists now, but is in the hallucination DB and brand new
            return Resp(200, {"info": {"project_urls": None, "home_page": ""},
                              "releases": {"0.0.1": [{"upload_time_iso_8601": iso(2)}]}})
        return Resp(404)
    if "registry.npmjs.org" in url:
        if url.endswith("/express"):
            return Resp(200, {"time": {"created": iso(5000)}, "dist-tags": {"latest": "4"},
                              "versions": {str(i): {"scripts": {}} for i in range(50)},
                              "repository": {"url": "x"}, "maintainers": [1, 2, 3]})
        return Resp(404)
    return Resp(404)


def check(cmd, expected):
    with patch("shield.requests.get", fake_get):
        got = {r["name"]: r["verdict"] for r in shield.analyze(cmd)}
    assert got == expected, f"{cmd!r}: expected {expected}, got {got}"
    print("PASS ", cmd, "->", got)


# parsing
assert shield.parse_command("pip install requests==2.31 'pandas>=2' -r req.txt --upgrade") == [("pypi", "requests"), ("pypi", "pandas")]
assert shield.parse_command("$ npm i -D @types/node@20 express") == [("npm", "@types/node"), ("npm", "express")]
assert shield.parse_command("python -m pip install flask[async]") == [("pypi", "flask")]
assert shield.parse_command("hello world") == []
print("PASS  parsing")

# verdicts
check("pip install requests", {"requests": "ALLOW"})
check("pip install does-not-exist-abc", {"does-not-exist-abc": "BLOCK"})
check("pip install sketchy-new-pkg", {"sketchy-new-pkg": "WARN"})
check("pip install pdf-reader-pro", {"pdf-reader-pro": "BLOCK"})
check("npm install express express-auth-helper", {"express": "ALLOW", "express-auth-helper": "BLOCK"})
print("\nAll tests passed.")
