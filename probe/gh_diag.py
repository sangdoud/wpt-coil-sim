# -*- coding: utf-8 -*-
"""诊断令牌到底能看见什么。绝不打印令牌本身。"""
import json
import os
import urllib.error
import urllib.request

TOKEN_FILE = r"C:\wpt\.gh_token"
REPO = "sangdoud/wpt-coil-sim"

tok = open(TOKEN_FILE, encoding="utf-8").read().strip()
print("令牌前缀: %s...  长度 %d" % (tok[:14], len(tok)))


def call(label, url):
    hdr = {"Authorization": "Bearer " + tok,
           "Accept": "application/vnd.github+json",
           "User-Agent": "dsh-diag",
           "X-GitHub-Api-Version": "2022-11-28"}
    try:
        req = urllib.request.Request(url, headers=hdr)
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            print("  %-34s STATUS %s" % (label, r.status))
            for h in ("x-oauth-scopes", "x-accepted-oauth-scopes", "x-ratelimit-remaining"):
                v = r.headers.get(h)
                if v is not None:
                    print("      %-26s %s" % (h, v))
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        print("  %-34s STATUS %s %s" % (label, e.code, e.reason))
        try:
            b = e.read().decode("utf-8", "replace")
            print("      BODY: %s" % b[:300])
        except Exception:
            pass
    except Exception as e:
        print("  %-34s FAIL %s %s" % (label, type(e).__name__, e))
    return None


print("\n=== 1. 令牌身份 ===")
u = call("GET /user", "https://api.github.com/user")
if u:
    print("      login=%s  type=%s" % (u.get("login"), u.get("type")))

print("\n=== 2. 目标仓库 ===")
r = call("GET /repos/%s" % REPO, "https://api.github.com/repos/%s" % REPO)
if r:
    print("      private=%s  permissions=%s" % (r.get("private"), r.get("permissions")))

print("\n=== 3. 令牌能看到的仓库（前 30 个）===")
repos = call("GET /user/repos?per_page=100", "https://api.github.com/user/repos?per_page=100&sort=updated")
if repos is not None:
    print("      可见仓库数 = %d" % len(repos))
    for x in repos[:30]:
        print("        - %s%s" % (x.get("full_name"), "  (private)" if x.get("private") else ""))

print("\n=== 4. 用户 sangdoud 是否存在 ===")
call("GET /users/sangdoud", "https://api.github.com/users/sangdoud")

print("\n=== 5. 按安装/组织路径再试一次仓库 ===")
call("GET /repos/sangdoud/wpt-coil-sim (重复)", "https://api.github.com/repos/sangdoud/wpt-coil-sim")
