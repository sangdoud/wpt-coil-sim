# -*- coding: utf-8 -*-
r"""模型备份 + 上传 GitHub（sangdoud/wpt-coil-sim，私有）。

两种模式：
  python gh_backup_model.py --local-only    只做本地备份（不需要令牌）
  python gh_backup_model.py --upload        本地备份 + 上传到 GitHub（需要令牌）

令牌来源（按顺序）：
  1. 环境变量 GH_TOKEN / GITHUB_TOKEN
  2. C:\wpt\.gh_token 文件（已加入 .gitignore，不会提交）
绝不打印令牌本身。

上传内容：
  model_snapshots/Projecttonight_20260916_width2mm.aedt.zip   压缩后的模型快照（6.8MB）
  model_snapshots/README.md                                    快照索引
  reports/线圈线宽2mm改造报告_20260916.md                        改造报告
  results/solve_width2.csv / solve_width3.csv                  A/B 原始数据
  + 复用 backup_upload.run_backup() 推 CSV/日志（原有约定）
"""

import base64
import hashlib
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

WPT = r"C:\wpt"
WORK = r"C:\ansys maxwell2024\_work"
MODEL = os.path.join(WPT, "Projecttonight.aedt")
REPORT = r"C:\ansys maxwell2024\线圈线宽2mm改造报告_20260916.md"
BATCH = os.path.join(WPT, "batch_sweep_unit30.py")
REPO = "sangdoud/wpt-coil-sim"
RELEASE_TAG = "snapshot-20260916-width2mm"
RELEASE_NAME = "模型快照 2026-09-16 · 线圈线宽 2mm"
ASSET_NAME = "Projecttonight_20260916_width2mm.aedt"
SNAP_DIR = os.path.join(WPT, "backup", "after_width2_20260916")
MODEL_TAG = "Projecttonight_20260916_width2mm"
TOKEN_FILE = os.path.join(WPT, ".gh_token")
LOG = os.path.join(WORK, "gh_backup.log")

UPLOADS = [
    # (本地绝对路径, 仓库内路径)
    (os.path.join(WORK, "%s.aedt.zip" % MODEL_TAG), "model_snapshots/%s.aedt.zip" % MODEL_TAG),
    (os.path.join(WORK, "SNAPSHOTS_README.md"), "model_snapshots/README.md"),
    (REPORT, "reports/线圈线宽2mm改造报告_20260916.md"),
    (os.path.join(WORK, "solve_width2.csv"), "results/solve_width2.csv"),
    (os.path.join(WORK, "solve_width3.csv"), "results/solve_width3.csv"),
    (os.path.join(WORK, "coil_paths.json"), "model_snapshots/coil_paths_20260916.json"),
]


def log(m):
    line = "%s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), m)
    print(line, flush=True)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def get_token():
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(var)
        if v and v.strip():
            return v.strip(), "环境变量 %s" % var
    if os.path.isfile(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as f:
            v = f.read().strip()
        if v:
            return v, TOKEN_FILE
    return None, None


# ---------------------------------------------------------------- 本地备份
def local_backup():
    os.makedirs(SNAP_DIR, exist_ok=True)
    log("=== 本地备份 -> %s ===" % SNAP_DIR)
    items = [(MODEL, "Projecttonight.aedt"), (BATCH, "batch_sweep_unit30.py"),
             (REPORT, "线圈线宽2mm改造报告_20260916.md"),
             (os.path.join(WORK, "solve_width2.csv"), "solve_width2.csv"),
             (os.path.join(WORK, "solve_width3.csv"), "solve_width3.csv")]
    for src, dst in items:
        if not os.path.exists(src):
            log("  跳过（不存在）: %s" % src)
            continue
        shutil.copy2(src, os.path.join(SNAP_DIR, dst))
        log("  %-40s %8.2f MB" % (dst, os.path.getsize(src) / 1048576.0))
    # 压缩快照也放一份到本地备份目录
    zpath = os.path.join(WORK, "%s.aedt.zip" % MODEL_TAG)
    if os.path.exists(zpath):
        shutil.copy2(zpath, os.path.join(SNAP_DIR, os.path.basename(zpath)))
        log("  %-40s %8.2f MB" % (os.path.basename(zpath), os.path.getsize(zpath) / 1048576.0))
    log("  模型 md5 = %s" % md5(MODEL))
    return True


def make_snapshot_zip():
    zpath = os.path.join(WORK, "%s.aedt.zip" % MODEL_TAG)
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.write(MODEL, "Projecttonight.aedt")
    log("快照压缩包 %s  %.2f MB (原始 %.2f MB)"
        % (os.path.basename(zpath), os.path.getsize(zpath) / 1048576.0,
           os.path.getsize(MODEL) / 1048576.0))
    return zpath


def write_readme():
    p = os.path.join(WORK, "SNAPSHOTS_README.md")
    m = md5(MODEL)
    size = os.path.getsize(MODEL)
    txt = f"""# 模型快照索引

每个 `*.aedt.zip` 是一个 `Projecttonight.aedt` 的完整快照（zip 内文件名固定为
`Projecttonight.aedt`），解压后直接就是可用的 Maxwell 工程。
压缩率约 10%（原始 .aedt 是文本格式），所以放仓库里比直接提交原始大文件省得多。

| 快照 | 日期 | 内容 | 原始大小 | md5 |
|---|---|---|---|---|
| `{MODEL_TAG}.aedt.zip` | 2026-09-16 | 线圈线宽 3mm → **2mm**（Tx1/Tx2/Rx），线厚 0.5mm 不变；批次脚本 `COIL_SIZE` 同步为 167.90 | {size} bytes | `{m}` |

## 恢复方法

```powershell
Expand-Archive {MODEL_TAG}.aedt.zip -DestinationPath C:\\wpt -Force
```

注意：解压前先关掉 AEDT，并确认没有 `Projecttonight.aedt.lock`。

## 相关说明

- 改造报告见 `reports/线圈线宽2mm改造报告_20260916.md`
- 同一点的 2mm / 3mm A/B 电感数据见 `results/solve_width2.csv`、`results/solve_width3.csv`
- 线圈原始路径（768 点 × 3）见 `model_snapshots/coil_paths_20260916.json`
- 这个模型**不含**求解结果（`.aedtresults` 未打包）
"""
    with open(p, "w", encoding="utf-8") as f:
        f.write(txt)
    return p


# ---------------------------------------------------------------- GitHub API
def api(method, path, token, payload=None, timeout=300):
    url = "https://api.github.com" + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "wpt-model-backup",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return json.loads(body.decode("utf-8")) if body else {}


def blob_sha(data):
    h = hashlib.sha1()
    h.update(b"blob %d\x00" % len(data))
    h.update(data)
    return h.hexdigest()


def upload(token, token_src):
    log("令牌来源: %s（长度 %d，不打印内容）" % (token_src, len(token)))
    repo = api("GET", "/repos/%s" % REPO, token)
    log("仓库 %s  private=%s  默认分支=%s  权限 push=%s"
        % (REPO, repo.get("private"), repo.get("default_branch"),
           (repo.get("permissions") or {}).get("push")))
    if not (repo.get("permissions") or {}).get("push"):
        log("!! 这个令牌没有 push 权限（需要 Contents: Read and write）")
        return False

    branch = repo.get("default_branch") or "master"
    ref = api("GET", "/repos/%s/git/ref/heads/%s" % (REPO, branch), token)
    parent = ref["object"]["sha"]
    commit = api("GET", "/repos/%s/git/commits/%s" % (REPO, parent), token)
    base_tree = commit["tree"]["sha"]
    tree = api("GET", "/repos/%s/git/trees/%s?recursive=1" % (REPO, base_tree), token)
    remote = {e["path"]: e["sha"] for e in tree.get("tree", []) if e.get("type") == "blob"}
    log("远端当前 %d 个文件，父提交 %s" % (len(remote), parent[:10]))

    entries, changed = [], []
    for lp, rp in UPLOADS:
        if not os.path.exists(lp):
            log("  跳过（本地不存在）: %s" % lp)
            continue
        with open(lp, "rb") as f:
            data = f.read()
        if remote.get(rp) == blob_sha(data):
            log("  未变化: %s" % rp)
            continue
        blob = api("POST", "/repos/%s/git/blobs" % REPO, token, {
            "content": base64.b64encode(data).decode("ascii"), "encoding": "base64"})
        entries.append({"path": rp, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        changed.append("%s (%.2f MB)" % (rp, len(data) / 1048576.0))
        log("  已建 blob: %s  %.2f MB" % (rp, len(data) / 1048576.0))

    if not entries:
        log("模型/报告均已是最新，无新增提交")
    else:
        new_tree = api("POST", "/repos/%s/git/trees" % REPO, token,
                       {"base_tree": base_tree, "tree": entries})
        msg = "模型快照 %s（线宽 2mm）+ 改造报告 + A/B 数据" % MODEL_TAG
        nc = api("POST", "/repos/%s/git/commits" % REPO, token,
                 {"message": msg, "tree": new_tree["sha"], "parents": [parent]})
        api("PATCH", "/repos/%s/git/refs/heads/%s" % (REPO, branch), token,
            {"sha": nc["sha"]})
        log("已推送 %d 个文件到 %s@%s" % (len(entries), REPO, branch))
        for c in changed:
            log("    + %s" % c)
        log("commit https://github.com/%s/commit/%s" % (REPO, nc["sha"]))

    # 原有约定：CSV / 日志也走一次 backup_upload
    try:
        sys.path.insert(0, WPT)
        import backup_upload
        log("调用原有 backup_upload.run_backup() ...")
        backup_upload.run_backup()
    except Exception as e:
        log("backup_upload 调用失败（不影响模型快照）: %s %s" % (type(e).__name__, e))

    # 原始 .aedt 作为 Release 附件（Release 附件单文件上限 2GB，不占仓库工作树）
    upload_release(token, branch)
    return True


# ---------------------------------------------------------------- Release 附件
def upload_asset(url, token, path, timeout=1800):
    """把本地文件 POST 成 release asset。

    注意：**不要自己设 Content-Length** —— http.client 会按 body 长度自己加，
    手写一个会变成重复头，GitHub 直接回 400 Bad Content-Length（踩过一次）。
    """
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        data = f.read()
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "User-Agent": "wpt-model-backup",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/octet-stream",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    assert len(data) == size
    return json.loads(body.decode("utf-8")) if body else {}


def upload_release(token, branch):
    log("")
    log("=== Release 附件（原始 .aedt）===")
    try:
        rel = api("GET", "/repos/%s/releases/tags/%s" % (REPO, RELEASE_TAG), token)
        log("  Release %s 已存在 (id=%s)" % (RELEASE_TAG, rel.get("id")))
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        m = md5(MODEL)
        rel = api("POST", "/repos/%s/releases" % REPO, token, {
            "tag_name": RELEASE_TAG,
            "target_commitish": branch,
            "name": RELEASE_NAME,
            "draft": False,
            "prerelease": False,
            "body": ("线圈线宽 3mm → 2mm（Tx1/Tx2/Rx），线厚 0.5mm 不变。\n\n"
                     "- 设计：WPT_G（Maxwell 3D Magnetostatic）\n"
                     "- 原始大小：%d bytes，md5 `%s`\n"
                     "- 批次脚本 `COIL_SIZE` 同步为 167.90\n"
                     "- 同点 A/B：L11 19.968→20.303 µH，L33 24.100→24.606 µH，k13 0.15500→0.15113\n"
                     "- 改造报告：`reports/线圈线宽2mm改造报告_20260916.md`\n"
                     % (os.path.getsize(MODEL), m)),
        })
        log("  已创建 Release %s (id=%s)" % (RELEASE_TAG, rel.get("id")))

    for a in rel.get("assets", []):
        if a.get("name") == ASSET_NAME:
            api("DELETE", "/repos/%s/releases/assets/%d" % (REPO, a["id"]), token)
            log("  删除同名旧附件 %s" % ASSET_NAME)

    url = "https://uploads.github.com/repos/%s/releases/%d/assets?name=%s" % (
        REPO, rel["id"], urllib.parse.quote(ASSET_NAME))
    t0 = time.time()
    log("  正在上传 %.2f MB ..." % (os.path.getsize(MODEL) / 1048576.0))
    a = upload_asset(url, token, MODEL)
    log("  已上传附件 %s (%.2f MB, %.0fs)" % (a.get("name"),
                                              (a.get("size") or 0) / 1048576.0, time.time() - t0))
    log("  下载地址 %s" % a.get("browser_download_url"))

    # 复核：重新拉一次 release，确认附件真的在、大小对得上
    rel2 = api("GET", "/repos/%s/releases/tags/%s" % (REPO, RELEASE_TAG), token)
    for x in rel2.get("assets", []):
        log("  复核附件: %-52s %10d bytes  state=%s  downloads=%s"
            % (x.get("name"), x.get("size") or 0, x.get("state"), x.get("download_count")))
    return a


def main():
    mode = "--upload" if "--upload" in sys.argv else "--local-only"
    log("=" * 70)
    log("模型备份  mode=%s" % mode)
    if not os.path.exists(MODEL):
        log("!! 找不到模型 %s" % MODEL)
        return 1
    make_snapshot_zip()
    write_readme()
    local_backup()

    if mode != "--upload":
        log("本地备份完成（未上传）。加 --upload 并配好令牌即会上传。")
        return 0

    token, src = get_token()
    if not token:
        log("!! 找不到令牌：环境变量 GH_TOKEN / GITHUB_TOKEN 都没有，%s 也不存在" % TOKEN_FILE)
        log("   请把 PAT 写进 %s（只含令牌一行），再重跑 --upload" % TOKEN_FILE)
        return 2
    try:
        ok = upload(token, src)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        log("!! HTTP %s %s :: %s" % (e.code, e.reason, body))
        if e.code == 401:
            log(">> 令牌无效或过期")
        elif e.code == 403:
            log(">> 权限不足（Contents: Read and write）或限流")
        return 1
    except Exception as e:
        log("!! 上传失败: %s %s" % (type(e).__name__, e))
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
