"""Who is this token, and exactly what can it touch? Never prints the token."""

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


print("=== identity ===")
try:
    with api("/user") as r:
        me = json.load(r)
        print("login :", me.get("login"))
        print("id    :", me.get("id"))
        print("scopes:", r.headers.get("x-oauth-scopes"))
except Exception as e:
    print("FAIL", type(e).__name__, e)
    sys.exit(1)

login = me.get("login")

print()
print("=== repo counts for %s ===" % login)
try:
    with api("/users/" + login) as r:
        d = json.load(r)
    for k in ("public_repos", "total_private_repos", "owned_private_repos"):
        print("  %-20s %s" % (k, d.get(k, "<absent>")))
except Exception as e:
    print("  FAIL", type(e).__name__, e)

print()
print("=== repos visible to THIS token ===")
try:
    with api("/user/repos?per_page=100&visibility=all&affiliation=owner,collaborator,organization_member") as r:
        repos = json.load(r)
    print("  count =", len(repos))
    for x in repos:
        print("    %s  private=%s" % (x.get("full_name"), x.get("private")))
except Exception as e:
    print("  FAIL", type(e).__name__, e)

print()
print("=== orgs this token can see ===")
try:
    with api("/user/orgs") as r:
        orgs = json.load(r)
    print("  count =", len(orgs))
    for o in orgs:
        print("   ", o.get("login"))
except Exception as e:
    print("  FAIL", type(e).__name__, e)

print()
print("=== probe repo names under every visible owner ===")
owners = [login] + [o.get("login") for o in (orgs if isinstance(orgs, list) else [])]
cands = ["wpt-coil-sim", "wpt_coil_sim", "wpt-coilsim", "wpt-coil", "coil-sim",
         "wpt", "wpt-sim", "maxwell-wpt", "wpt_coil_simulation"]
for owner in owners:
    for c in cands:
        try:
            with api("/repos/%s/%s" % (owner, c)) as r:
                d = json.load(r)
                print("  FOUND %s private=%s size=%s" % (d.get("full_name"), d.get("private"), d.get("size")))
        except urllib.error.HTTPError as e:
            if e.code != 404:
                print("  %s/%s -> HTTP %s" % (owner, c, e.code))
        except Exception:
            pass
print("  (probe complete; only 404s were silent)")
