"""Re-test the git smart-HTTP 403-vs-404 difference, with pacing so GitHub's
secondary (abuse) rate limiter does not confound the result.
Never prints the token.
"""

import base64
import os
import time
import urllib.error
import urllib.request

TOKEN = os.environ.get("GH_TOKEN", "")
USER = "sangdoud"
BASIC = base64.b64encode(("%s:%s" % (USER, TOKEN)).encode()).decode()

CASES = [
    ("target   wpt-coil-sim", "wpt-coil-sim"),
    ("bogus    zzz-not-real-9f3a2b", "zzz-not-real-9f3a2b"),
    ("public   web-platform-tests/wpt", None),
]


def probe(label, url, auth):
    headers = {"User-Agent": "git/2.43.0", "Accept": "*/*"}
    if auth:
        headers["Authorization"] = "Basic " + BASIC
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("  %-34s -> %s" % (label, r.status))
            return r.status
    except urllib.error.HTTPError as e:
        print("  %-34s -> %s %s" % (label, e.code, e.reason))
        return e.code
    except Exception as e:
        print("  %-34s -> FAIL %s" % (label, type(e).__name__))
        return None


print("=== git smart-HTTP, paced ===")
for label, name in CASES:
    if name is None:
        owner, repo = "web-platform-tests", "wpt"
    else:
        owner, repo = USER, name
    url = "https://github.com/%s/%s.git/info/refs?service=git-upload-pack" % (owner, repo)
    probe(label + "  (anon)", url, auth=False)
    time.sleep(6)
    probe(label + "  (token)", url, auth=True)
    time.sleep(10)

print()
print("=== REST, paced ===")
for label, name in CASES:
    if name is None:
        path = "/repos/web-platform-tests/wpt"
    else:
        path = "/repos/%s/%s" % (USER, name)
    probe(label, "https://api.github.com" + path, auth=True)
    time.sleep(6)
