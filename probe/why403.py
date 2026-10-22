"""Inspect the exact 403: rate limit, revoked token, or genuine forbidden?
Never prints the token.
"""

import os
import sys
import urllib.error
import urllib.request

TOKEN = os.environ.get("GH_TOKEN")
if not TOKEN:
    print("NO TOKEN")
    sys.exit(2)

HDR = {
    "Authorization": "Bearer " + TOKEN,
    "Accept": "application/vnd.github+json",
    "User-Agent": "dsh-deploy",
    "X-GitHub-Api-Version": "2022-11-28",
}


def call(label, url):
    print("--- %s" % label)
    print("    %s" % url)
    try:
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=30) as r:
            print("    STATUS %s" % r.status)
            for h in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
                      "x-oauth-scopes", "retry-after"):
                v = r.headers.get(h)
                if v is not None:
                    print("    %-22s %s" % (h, v))
            return
    except urllib.error.HTTPError as e:
        print("    STATUS %s %s" % (e.code, e.reason))
        for h in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-reset",
                  "x-oauth-scopes", "retry-after"):
            v = e.headers.get(h)
            if v is not None:
                print("    %-22s %s" % (h, v))
        body = e.read().decode("utf-8", "replace")
        print("    BODY: %s" % body[:500])
    except Exception as e:
        print("    FAIL %s %s" % (type(e).__name__, e))


print("=== rate limit status ===")
call("GET /rate_limit", "https://api.github.com/rate_limit")

print()
print("=== identity ===")
call("GET /user", "https://api.github.com/user")

print()
print("=== target repo ===")
call("GET /repos/sangdoud/wpt-coil-sim", "https://api.github.com/repos/sangdoud/wpt-coil-sim")

print()
print("=== nonexistent control ===")
call("GET /repos/sangdoud/zzz-not-real-9f3a2b", "https://api.github.com/repos/sangdoud/zzz-not-real-9f3a2b")

print()
print("=== public control ===")
call("GET /repos/web-platform-tests/wpt", "https://api.github.com/repos/web-platform-tests/wpt")
