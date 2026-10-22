"""Discriminating probe: does GitHub treat 'wpt-coil-sim' differently from a
name that certainly does not exist? Compares anonymous and authenticated git
smart-HTTP endpoints. Never prints the token.
"""

import base64
import os
import urllib.error
import urllib.request

TOKEN = os.environ.get("GH_TOKEN", "")
USER = "sangdoud"

TARGET = "wpt-coil-sim"
BOGUS = "zzz-definitely-not-a-real-repo-9f3a2b"

BASIC = base64.b64encode(("%s:%s" % (USER, TOKEN)).encode()).decode()


def probe(label, url, auth):
    headers = {
        "User-Agent": "git/2.43.0",
        "Accept": "*/*",
    }
    if auth:
        headers["Authorization"] = "Basic " + BASIC
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("  %-46s -> %s" % (label, r.status))
    except urllib.error.HTTPError as e:
        wa = e.headers.get("WWW-Authenticate")
        print("  %-46s -> %s %s%s" % (label, e.code, e.reason, ("  [WWW-Auth: %s]" % wa) if wa else ""))
    except Exception as e:
        print("  %-46s -> FAIL %s" % (label, type(e).__name__))


print("=== git smart-HTTP: info/refs (upload-pack) ===")
for name in (TARGET, BOGUS):
    url = "https://github.com/%s/%s.git/info/refs?service=git-upload-pack" % (USER, name)
    probe("%s  (anonymous)" % name, url, auth=False)
    probe("%s  (with token)" % name, url, auth=True)

print()
print("=== REST API: repo metadata ===")
for name in (TARGET, BOGUS):
    probe("%s (api, with token)" % name,
          "https://api.github.com/repos/%s/%s" % (USER, name), auth=True)

print()
print("=== REST API: does the token see the owner profile's private counts? ===")
probe("api /users/%s" % USER, "https://api.github.com/users/%s" % USER, auth=True)
