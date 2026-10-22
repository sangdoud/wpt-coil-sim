"""GitHub device-flow login + fetch of the private repo.

  python device_login.py start   -> prints a URL + one-time code for the user
  python device_login.py poll    -> waits for approval, then downloads the repo

The access token is held in memory only and is never written to disk.
"""

import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

CLIENT_ID = "178c6fc778ccc68e1d6a"  # GitHub CLI's public OAuth client id
SCOPE = "repo"
STATE_FILE = r"C:\ansys maxwell2024\_probe\device_state.json"
REPO = "sangdoud/wpt-coil-sim"
DEST = r"C:\wpt"
TARGET_FILES = ["preflight_2025.py", "batch_sweep_unit30.py", "Projecttonight.aedt"]


def post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Accept": "application/json", "User-Agent": "dsh-deploy"},
    )
    return json.load(urllib.request.urlopen(req, timeout=30))


def get_json(url, token, timeout=120):
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


def cmd_start():
    d = post_form(
        "https://github.com/login/device/code",
        {"client_id": CLIENT_ID, "scope": SCOPE},
    )
    if "user_code" not in d:
        print("DEVICE CODE REQUEST FAILED:")
        print(json.dumps(d, indent=2))
        return 1
    with open(STATE_FILE, "w") as fh:
        json.dump(d, fh)
    print("=" * 56)
    print("  打开这个网址：", d["verification_uri"])
    print("  输入这个代码：", d["user_code"])
    print("  有效期      ：", d["expires_in"], "秒")
    print("=" * 56)
    return 0


def cmd_poll():
    if not os.path.isfile(STATE_FILE):
        print("NO STATE: run 'start' first")
        return 1
    with open(STATE_FILE) as fh:
        d = json.load(fh)

    interval = max(int(d.get("interval", 5)), 5)
    deadline = time.time() + int(d.get("expires_in", 900))
    token = None

    print("waiting for you to approve ...", flush=True)
    while time.time() < deadline:
        r = post_form(
            "https://github.com/login/oauth/access_token",
            {
                "client_id": CLIENT_ID,
                "device_code": d["device_code"],
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        if "access_token" in r:
            token = r["access_token"]
            print("AUTHORIZED. scope =", r.get("scope"))
            break
        err = r.get("error")
        if err == "authorization_pending":
            time.sleep(interval)
            continue
        if err == "slow_down":
            interval += 5
            time.sleep(interval)
            continue
        print("AUTH ERROR:", json.dumps(r))
        return 1
    if not token:
        print("TIMED OUT waiting for authorization")
        return 2

    # ---- confirm identity + access -----------------------------------------
    with get_json("https://api.github.com/user", token) as r:
        me = json.load(r)
    print("logged in as:", me.get("login"))

    with get_json("https://api.github.com/repos/" + REPO, token) as r:
        info = json.load(r)
    branch = info.get("default_branch", "main")
    print("repo   :", info.get("full_name"))
    print("private:", info.get("private"))
    print("branch :", branch)
    print("sizeKB :", info.get("size"))

    # ---- download zipball ---------------------------------------------------
    with get_json("https://api.github.com/repos/%s/zipball/%s" % (REPO, branch), token, timeout=600) as r:
        data = r.read()
    print("downloaded:", len(data), "bytes")

    # ---- extract ------------------------------------------------------------
    os.makedirs(DEST, exist_ok=True)
    written = 0
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
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

    # ---- inventory ----------------------------------------------------------
    print()
    print("=== C:\\wpt inventory ===")
    for root, _d, files in os.walk(DEST):
        for f in sorted(files):
            p = os.path.join(root, f)
            print("%12d  %s" % (os.path.getsize(p), p))

    print()
    print("=== required files ===")
    ok = True
    for name in TARGET_FILES:
        p = os.path.join(DEST, name)
        if os.path.isfile(p):
            print("OK      %s  (%d bytes)" % (p, os.path.getsize(p)))
        else:
            print("MISSING %s" % p)
            ok = False

    aedt = os.path.join(DEST, "Projecttonight.aedt")
    if os.path.isfile(aedt):
        with open(aedt, "rb") as fh:
            head = fh.read(120)
        if head.startswith(b"version https://git-lfs"):
            print("!! Projecttonight.aedt 是 Git-LFS 指针，不是真模型")
            ok = False
        else:
            print("Projecttonight.aedt 前 8 字节:", head[:8])

    return 0 if ok else 6


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("start", "poll"):
        print("usage: device_login.py start|poll")
        sys.exit(64)
    sys.exit(cmd_start() if sys.argv[1] == "start" else cmd_poll())
