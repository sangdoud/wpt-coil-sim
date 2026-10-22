"""Decisive follow-up: does sangdoud own any private repos, and can this token
read contents anywhere at all? Never prints the token.
"""

import json
import os
import sys
import urllib.error
import urllib.request

TOKEN = os.environ.get("GH_TOKEN")
if not TOKEN:
    print("NO TOKEN")
    sys.exit(2)


def api(path, timeout=60):
    req = urllib.request.Request(
        "https://api.github.com" + path,
        headers={
            "Authorization": "Bearer " + TOKEN,
            "Accept": "application/vnd.github+json",
            "User-Agent": "dsh-deploy",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def show(label, path):
    print("--- %s" % label)
    try:
        with api(path) as r:
            return json.load(r), dict(r.headers)
    except urllib.error.HTTPError as e:
        print("  HTTP %s %s :: %s" % (e.code, e.reason, e.read().decode("utf-8", "replace")[:200]))
    except Exception as e:
        print("  FAIL %s %s" % (type(e).__name__, e))
    return None, None


# 1. owner profile AS THE OWNER -> reveals private repo counts
data, _ = show("GET /users/sangdoud  (authenticated as owner)", "/users/sangdoud")
if data:
    for k in ("login", "public_repos", "total_private_repos", "owned_private_repos",
              "public_gists", "created_at", "updated_at"):
        if k in data:
            print("  %-22s %s" % (k, data[k]))

# 2. can the token read contents of a repo that definitely exists (public)?
print()
data, _ = show("GET /repos/web-platform-tests/wpt  (public control)", "/repos/web-platform-tests/wpt")
if data:
    print("  OK -> token plumbing works; full_name=%s private=%s" % (data.get("full_name"), data.get("private")))

# 3. list every repo visible to the token, all visibilities
print()
data, hdrs = show("GET /user/repos?visibility=all  (all visibilities)", "/user/repos?per_page=100&visibility=all")
if data is not None:
    print("  count =", len(data))
    for r in data:
        print("   ", r.get("full_name"), "private=", r.get("private"))

# 4. installations (fine-grained tokens tied to an org/app)
print()
data, _ = show("GET /user/installations", "/user/installations")
if data is not None:
    print("  total_count =", data.get("total_count"))

# 5. brute check a few plausible repo names as the owner
print()
print("--- direct repo probes (as owner) ---")
for name in ["wpt-coil-sim", "wpt_coil_sim", "WPT-Coil-Sim", "wpt-coilsim",
             "wpt-coil", "wpt-maxwell", "coil-sim", "wpt-simulation"]:
    try:
        with api("/repos/sangdoud/" + name) as r:
            d = json.load(r)
            print("  FOUND %s private=%s" % (d.get("full_name"), d.get("private")))
    except urllib.error.HTTPError as e:
        print("  %-20s HTTP %s" % (name, e.code))
    except Exception as e:
        print("  %-20s FAIL %s" % (name, type(e).__name__))
