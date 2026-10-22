"""Device-flow login, then restore ONLY Projecttonight.aedt from the repo.

  python restore_model.py start   -> prints URL + one-time code
  python restore_model.py poll    -> waits, then restores the file

Safety behaviour:
  * the current (modified) model is quarantined, never silently deleted
  * the run's autosave artefacts are moved aside (a .auto next to the project
    could be offered by AEDT as a recovery file and re-corrupt the model)
  * the restored file is verified against the known-good size and md5
  * a pristine read-only copy is placed in C:\\wpt\\backup

The access token is held in memory only; it is never written to disk.
"""

import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

CLIENT_ID = "178c6fc778ccc68e1d6a"  # GitHub CLI public OAuth client id
SCOPE = "repo"
STATE_FILE = r"C:\ansys maxwell2024\_probe\restore_state.json"

REPO = "sangdoud/wpt-coil-sim"
REPO_PATH = "Projecttonight.aedt"
DEST = r"C:\wpt\Projecttonight.aedt"
BACKUP_DIR = r"C:\wpt\backup"
INCIDENT_DIR = r"C:\wpt\_incident_20260913"

EXPECT_SIZE = 25155997
EXPECT_MD5 = "9bb98917d803ca42191a6abee8360d82"

QUARANTINE = [
    r"C:\wpt\Projecttonight.aedt",
    r"C:\wpt\Projecttonight.aedt.auto",
    r"C:\wpt\Projecttonight.pyaedt",
    r"C:\wpt\Projecttonight.aedtresults",
]


def post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url, data=body,
        headers={"Accept": "application/json", "User-Agent": "dsh-deploy"},
    )
    return json.load(urllib.request.urlopen(req, timeout=30))


def cmd_start():
    d = post_form("https://github.com/login/device/code",
                  {"client_id": CLIENT_ID, "scope": SCOPE})
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
        r = post_form("https://github.com/login/oauth/access_token", {
            "client_id": CLIENT_ID,
            "device_code": d["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        })
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

    # ---- download the single file as raw bytes ------------------------------
    print("downloading", REPO_PATH, "...")
    req = urllib.request.Request(
        "https://api.github.com/repos/%s/contents/%s" % (REPO, REPO_PATH),
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github.raw",
            "User-Agent": "dsh-deploy",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            data = r.read()
    except urllib.error.HTTPError as e:
        print("DOWNLOAD FAIL: HTTP %s %s" % (e.code, e.reason))
        print(e.read().decode("utf-8", "replace")[:400])
        return 3
    print("downloaded:", len(data), "bytes")

    # ---- verify BEFORE touching anything on disk ---------------------------
    import hashlib
    digest = hashlib.md5(data).hexdigest()
    print("size:", len(data), "(expect %d) -> %s" % (EXPECT_SIZE, "OK" if len(data) == EXPECT_SIZE else "MISMATCH"))
    print("md5 :", digest)
    print("     ", "(expect %s) -> %s" % (EXPECT_MD5, "OK" if digest == EXPECT_MD5 else "MISMATCH"))
    if len(data) != EXPECT_SIZE or digest != EXPECT_MD5:
        print("!! 下载内容与期望不一致，NOT restoring. 磁盘保持原样。")
        return 4

    # ---- quarantine current state ------------------------------------------
    os.makedirs(INCIDENT_DIR, exist_ok=True)
    print()
    print("=== quarantine ->", INCIDENT_DIR, "===")
    for p in QUARANTINE:
        if not os.path.exists(p):
            continue
        name = os.path.basename(p)
        target = os.path.join(INCIDENT_DIR, name)
        if os.path.exists(target):
            shutil.rmtree(target, ignore_errors=True) if os.path.isdir(target) else os.remove(target)
        shutil.move(p, target)
        print("  moved:", p, "->", target)

    # ---- restore ------------------------------------------------------------
    with open(DEST, "wb") as fh:
        fh.write(data)
    print()
    print("restored:", DEST)

    # ---- pristine read-only backup -----------------------------------------
    os.makedirs(BACKUP_DIR, exist_ok=True)
    bak = os.path.join(BACKUP_DIR, "Projecttonight.aedt")
    with open(bak, "wb") as fh:
        fh.write(data)
    try:
        os.chmod(bak, 0o444)
        print("backup (read-only):", bak)
    except Exception as e:
        print("backup:", bak, "(chmod failed:", e, ")")

    # ---- verify on disk -----------------------------------------------------
    h = hashlib.md5()
    with open(DEST, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    final = h.hexdigest()
    sz = os.path.getsize(DEST)
    print()
    print("=== final on-disk verification ===")
    print("size:", sz)
    print("md5 :", final)
    ok = (sz == EXPECT_SIZE and final == EXPECT_MD5)
    print("RESULT:", "RESTORED OK" if ok else "STILL MISMATCH")

    print()
    print("=== C:\\wpt now ===")
    for name in sorted(os.listdir(r"C:\wpt")):
        p = os.path.join(r"C:\wpt", name)
        if os.path.isfile(p):
            print("%12d  %s" % (os.path.getsize(p), name))
        else:
            print("%12s  %s\\" % ("<dir>", name))

    return 0 if ok else 5


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("start", "poll"):
        print("usage: restore_model.py start|poll")
        sys.exit(64)
    sys.exit(cmd_start() if sys.argv[1] == "start" else cmd_poll())
