# -*- coding: utf-8 -*-
"""端到端复核：把 GitHub 上的备份下载回来验 md5。
 1. 仓库树里确认 6 个文件在、大小对
 2. 下载 Release 附件（原始 .aedt）-> md5 必须等于本地
 3. 下载 model_snapshots 里的 zip -> 解出里面的 .aedt -> md5 必须等于本地
绝不打印令牌。"""
import hashlib
import io
import json
import os
import urllib.error
import urllib.request
import zipfile

TOKEN = open(r"C:\wpt\.gh_token", encoding="utf-8").read().strip()
REPO = "sangdoud/wpt-coil-sim"
LOCAL_MODEL = r"C:\wpt\Projecttonight.aedt"
WANT_MD5 = hashlib.md5(open(LOCAL_MODEL, "rb").read()).hexdigest().upper()
WANT_SIZE = os.path.getsize(LOCAL_MODEL)

WANT_PATHS = [
    "model_snapshots/Projecttonight_20260916_width2mm.aedt.zip",
    "model_snapshots/README.md",
    "model_snapshots/coil_paths_20260916.json",
    "reports/线圈线宽2mm改造报告_20260916.md",
    "results/solve_width2.csv",
    "results/solve_width3.csv",
]


def api(path, accept="application/vnd.github+json"):
    req = urllib.request.Request("https://api.github.com" + path, headers={
        "Authorization": "Bearer " + TOKEN, "Accept": accept,
        "User-Agent": "dsh-verify", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.read()


def md5(b):
    return hashlib.md5(b).hexdigest().upper()


print("本地模型: %d bytes  md5=%s" % (WANT_SIZE, WANT_MD5))
print()

print("=== 1. 仓库树 ===")
tree = json.loads(api("/repos/%s/git/trees/master?recursive=1" % REPO))
blobs = {e["path"]: e for e in tree.get("tree", []) if e.get("type") == "blob"}
print("  仓库共 %d 个文件" % len(blobs))
ok1 = True
for p in WANT_PATHS:
    e = blobs.get(p)
    if e:
        print("  ✓ %-56s %9d bytes" % (p, e.get("size", -1)))
    else:
        print("  ✗ %-56s 不在仓库里" % p)
        ok1 = False

print()
print("=== 2. Release 附件（原始 .aedt）===")
rel = json.loads(api("/repos/%s/releases/tags/snapshot-20260916-width2mm" % REPO))
asset = None
for a in rel.get("assets", []):
    if a["name"] == "Projecttonight_20260916_width2mm.aedt":
        asset = a
print("  Release: %s  附件数=%d" % (rel.get("name"), len(rel.get("assets", []))))
ok2 = False
if asset:
    print("  附件: %s  %d bytes  state=%s" % (asset["name"], asset["size"], asset["state"]))
    data = api("/repos/%s/releases/assets/%d" % (REPO, asset["id"]), "application/octet-stream")
    print("  已下载 %d bytes" % len(data))
    got = md5(data)
    ok2 = (got == WANT_MD5 and len(data) == WANT_SIZE)
    print("  下载后 md5=%s  %s" % (got, "✓ 与本地一致" if ok2 else "✗ 不一致！"))
else:
    print("  ✗ 找不到附件")

print()
print("=== 3. 仓库里的压缩快照 ===")
ok3 = False
try:
    z = api("/repos/%s/contents/model_snapshots/Projecttonight_20260916_width2mm.aedt.zip" % REPO,
            "application/vnd.github.raw")
    print("  已下载 zip %d bytes" % len(z))
    with zipfile.ZipFile(io.BytesIO(z)) as zf:
        names = zf.namelist()
        print("  zip 内: %s" % names)
        inner = zf.read("Projecttonight.aedt")
    got = md5(inner)
    ok3 = (got == WANT_MD5 and len(inner) == WANT_SIZE)
    print("  解出 .aedt %d bytes  md5=%s  %s" % (len(inner), got, "✓ 与本地一致" if ok3 else "✗ 不一致！"))
except Exception as e:
    print("  ✗ %s %s" % (type(e).__name__, e))

print()
print("=== 结论 ===")
print("  仓库文件齐全: %s" % ("✓" if ok1 else "✗"))
print("  Release 附件可下载且内容一致: %s" % ("✓" if ok2 else "✗"))
print("  压缩快照可解压且内容一致: %s" % ("✓" if ok3 else "✗"))
print("  总体: %s" % ("备份可用 ✓" if (ok1 and ok2 and ok3) else "有问题 ✗"))
