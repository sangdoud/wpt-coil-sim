"""Read-only diagnostic: which account is this token, and what repos can it see?
Never prints the token itself.
"""

import json
import os
import sys
import urllib.error
import urllib.request

TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
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
    print("--- %s  [%s] ---" % (label, path))
    try:
        with api(path) as r:
            data = json.load(r)
        return data
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print("HTTP %s %s" % (e.code, e.reason))
        print(body[:400])
    except Exception as e:
        print("FAIL %s %s" % (type(e).__name__, e))
    return None


print("=== token identity ===")
me = show("authenticated user", "/user")
if me:
    print("login      :", me.get("login"))
    print("name       :", me.get("name"))
    print("type       :", me.get("type"))
    print("id         :", me.get("id"))

# scopes (classic PATs report this; fine-grained tokens show what they show)
print()
print("=== token scopes / rate limit ===")
try:
    req = urllib.request.Request(
        "https://api.github.com/user",
        headers={"Authorization": "Bearer " + TOKEN, "User-Agent": "dsh-deploy"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        print("x-oauth-scopes :", r.headers.get("x-oauth-scopes"))
        print("x-ratelimit-remaining:", r.headers.get("x-ratelimit-remaining"))
except Exception as e:
    print("FAIL", type(e).__name__, e)

print()
print("=== repos this token can see (owner/collaborator/org) ===")
seen = []
page = 1
while page <= 10:
    data = show("repos page %d" % page, "/user/repos?per_page=100&affiliation=owner,collaborator,organization_member&page=%d" % page)
    if not data:
        break
    for r in data:
        seen.append(r)
    if len(data) < 100:
        break
    page += 1

if seen:
    print()
    print("total visible: %d" % len(seen))
    for r in seen:
        print("  %-45s private=%-5s size=%-8s pushed=%s" % (
            r.get("full_name"), r.get("private"), r.get("size"), r.get("pushed_at")))
else:
    print("(none visible)")

print()
print("=== direct probes ===")
for path in [
    "/repos/sangdoud/wpt-coil-sim",
    "/repos/sangdoud/wpt-coil-sim/contents",
]:
    show(path, path)

print()
print("=== search: wpt in name (all owners) ===")
data = show("search", "/search/repositories?q=wpt+in:name&per_page=30")
if data:
    print("total_count:", data.get("total_count"))
    for r in data.get("items", []):
        print("  %-50s private=%s" % (r.get("full_name"), r.get("private")))

print()
print("=== search: coil sim ===")
data = show("search", "/search/repositories?q=coil+sim+in:name&per_page=30")
if data:
    print("total_count:", data.get("total_count"))
    for r in data.get("items", []):
        print("  %-50s private=%s" % (r.get("full_name"), r.get("private")))
