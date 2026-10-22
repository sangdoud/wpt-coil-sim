# -*- coding: utf-8 -*-
"""上传前的可行性检查：网络能不能到 api.github.com、模型压缩后多大、仓库可见性。
不打印任何令牌。"""
import json
import os
import urllib.error
import urllib.request
import zipfile
import time

MODEL = r"C:\wpt\Projecttonight.aedt"
OUT_ZIP = r"C:\ansys maxwell2024\_work\model_snapshot.zip"
REPO = "sangdoud/wpt-coil-sim"


def call(label, url, token=None):
    hdr = {"Accept": "application/vnd.github+json", "User-Agent": "dsh-backup"}
    if token:
        hdr["Authorization"] = "Bearer " + token
    try:
        req = urllib.request.Request(url, headers=hdr)
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8", "replace")
            print("  %-28s STATUS %s" % (label, r.status))
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        print("  %-28s STATUS %s %s" % (label, e.code, e.reason))
        try:
            print("      BODY: %s" % e.read().decode("utf-8", "replace")[:200])
        except Exception:
            pass
    except Exception as e:
        print("  %-28s FAIL %s %s" % (label, type(e).__name__, e))
    return None


print("=== 1. 网络到 GitHub API ===")
call("rate_limit(匿名)", "https://api.github.com/rate_limit")
r = call("目标仓库(匿名)", "https://api.github.com/repos/%s" % REPO)
if r:
    print("      可见性 private=%s  默认分支=%s  大小=%s KB" % (r.get("private"), r.get("default_branch"), r.get("size")))

print("")
print("=== 2. 模型压缩 ===")
t0 = time.time()
with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    z.write(MODEL, "Projecttonight.aedt")
raw = os.path.getsize(MODEL)
zsz = os.path.getsize(OUT_ZIP)
print("  原始  %.1f MB" % (raw / 1048576.0))
print("  压缩  %.1f MB  (%.1f%%，耗时 %.1fs)" % (zsz / 1048576.0, 100.0 * zsz / raw, time.time() - t0))
print("  路径  %s" % OUT_ZIP)

print("")
print("=== 3. 令牌 ===")
tok = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
print("  环境变量 GH_TOKEN/GITHUB_TOKEN: %s" % ("有" if tok else "无"))
print("  文件 C:\\wpt\\.gh_token: %s" % ("有" if os.path.isfile(r"C:\wpt\.gh_token") else "无"))
