"""Fetch the private repo sangdoud/wpt-coil-sim into C:\\wpt using only the
standard library (no git required, no new packages installed).

Usage:
    python fetch_repo.py <TOKEN>
or  set GH_TOKEN / GITHUB_TOKEN in the environment and run without args.

This only READS from GitHub. It never writes .aedt files and never launches AEDT.
"""

import io
import json
import os
import sys
import zipfile
import urllib.error
import urllib.request

REPO = "sangdoud/wpt-coil-sim"
DEST = r"C:\wpt"

TARGET_FILES = [
    "preflight_2025.py",
    "batch_sweep_unit30.py",
    "Projecttonight.aedt",
]


def get_token():
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    for var in ("GH_TOKEN", "GITHUB_TOKEN", "GH_PAT"):
        val = os.environ.get(var)
        if val and val.strip():
            return val.strip()
    return None


def api_get(url, token, timeout=60):
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "dsh-deploy",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    return urllib.request.urlopen(req, timeout=timeout)


def main():
    token = get_token()
    if not token:
        print("NO TOKEN: pass as argv[1] or set GH_TOKEN / GITHUB_TOKEN")
        return 2

    # ---- 1. confirm access to the private repo -------------------------------
    print("=== 1. repo access check ===")
    try:
        with api_get("https://api.github.com/repos/" + REPO, token) as r:
            info = json.load(r)
    except urllib.error.HTTPError as e:
        print("REPO ACCESS FAIL: HTTP %s %s" % (e.code, e.reason))
        body = e.read().decode("utf-8", "replace")
        print(body[:600])
        if e.code == 401:
            print(">> token 无效或已过期")
        elif e.code == 404:
            print(">> token 有效但看不到该仓库（权限不足 / 仓库名不对 / 未授权 SSO）")
        return 3
    except Exception as e:
        print("REPO ACCESS FAIL: %s %s" % (type(e).__name__, e))
        return 3

    branch = info.get("default_branch", "main")
    print("repo        :", info.get("full_name"))
    print("private     :", info.get("private"))
    print("default     :", branch)
    print("size(KB)    :", info.get("size"))
    print("pushed_at   :", info.get("pushed_at"))

    # ---- 2. download zipball ------------------------------------------------
    print()
    print("=== 2. download zipball ===")
    zip_url = "https://api.github.com/repos/%s/zipball/%s" % (REPO, branch)
    try:
        with api_get(zip_url, token, timeout=300) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        print("DOWNLOAD FAIL: HTTP %s %s" % (e.code, e.reason))
        return 4
    except Exception as e:
        print("DOWNLOAD FAIL: %s %s" % (type(e).__name__, e))
        return 4
    print("downloaded  :", len(data), "bytes")

    # ---- 3. extract into C:\wpt (strip the GitHub top-level folder) ---------
    print()
    print("=== 3. extract to %s ===" % DEST)
    os.makedirs(DEST, exist_ok=True)
    written = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        if not names:
            print("ZIP EMPTY")
            return 5
        top = names[0].split("/")[0] + "/"
        for n in names:
            if not n.startswith(top) or n == top:
                continue
            rel = n[len(top):]
            if not rel:
                continue
            target = os.path.join(DEST, rel.replace("/", os.sep))
            if n.endswith("/"):
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with z.open(n) as src, open(target, "wb") as dst:
                dst.write(src.read())
            written += 1
    print("files written:", written)

    # ---- 4. inventory -------------------------------------------------------
    print()
    print("=== 4. C:\\wpt inventory ===")
    for root, _dirs, files in os.walk(DEST):
        for f in sorted(files):
            p = os.path.join(root, f)
            try:
                sz = os.path.getsize(p)
            except OSError:
                sz = -1
            print("%12d  %s" % (sz, p))

    # ---- 5. required files present? ----------------------------------------
    print()
    print("=== 5. required files ===")
    ok = True
    for name in TARGET_FILES:
        p = os.path.join(DEST, name)
        if os.path.isfile(p):
            print("OK      %s  (%d bytes)" % (p, os.path.getsize(p)))
        else:
            print("MISSING %s" % p)
            ok = False

    # ---- 6. LFS pointer guard (a git-LFS pointer would break the md5) ------
    print()
    print("=== 6. LFS pointer check on Projecttonight.aedt ===")
    aedt = os.path.join(DEST, "Projecttonight.aedt")
    if os.path.isfile(aedt):
        with open(aedt, "rb") as fh:
            head = fh.read(200)
        if head.startswith(b"version https://git-lfs"):
            print("!! 这是 Git-LFS 指针文件，不是真模型 —— md5 必然对不上")
            print(head.decode("utf-8", "replace"))
            ok = False
        else:
            print("不是 LFS 指针，是真实二进制内容 (前 8 字节: %r)" % head[:8])
    else:
        print("(文件不存在，跳过)")

    return 0 if ok else 6


if __name__ == "__main__":
    sys.exit(main())
