# -*- coding: utf-8 -*-
"""每小时自动备份：把结果 CSV / 日志提交并推送到 GitHub。

背景
----
`batch_sweep_unit30.py` 会在每满 3600 秒时调用 `run_backup()`。
原实现（git 本地提交 + gh 上传）在本机无法工作 —— 这台服务器
**没有 git，也没有 gh**。所以这里直接走 GitHub REST API 的 Git Data API：
先建 blob、再建 tree、再建 commit、最后移动 ref，**一次产生一个原子提交**，
只用 Python 标准库，不安装任何新软件。

令牌
----
需要 `Contents: Read and write` 权限。按以下顺序查找：

  1. 环境变量 `GH_TOKEN` / `GITHUB_TOKEN`
  2. 同目录下的 `.gh_token` 文件（已加入 .gitignore，不会提交）

建议使用**细粒度 PAT**，Repository access 只选 `wpt-coil-sim`，
Permissions → Repository permissions → Contents = Read and write。
不要用带全账号 `repo` 范围的经典令牌。

行为
----
* 只备份结果与日志，**不碰 25MB 的 .aedt**（避免仓库历史被撑爆）。
* 逐文件比对本地 blob SHA 与远端 SHA，无变化就不提交、不产生空 commit。
* 任何失败只记录日志，**绝不抛出到调用方**，不会拖垮正在跑的批量任务。
"""

import base64
import glob
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

# ---------------- 配置 ----------------
REPO = "sangdoud/wpt-coil-sim"
DEFAULT_BRANCH = "master"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(BASE_DIR, ".gh_token")
LOG_FILE = os.path.join(BASE_DIR, "backup_upload.log")

# 要备份的文件（相对 BASE_DIR 的 glob，只匹配顶层）
BACKUP_PATTERNS = [
    "sweep_all_*.csv",
    "combos_*.csv",
    "scan_*.csv",
    "Lmatrix*.csv",
    "training_data.csv",
    "*.log",
]

EXCLUDE = {
    ".gh_token",
    "backup_upload.log",
    "batch.log",
}

MAX_FILE_MB = 20          # 单个文件上限，超过则跳过
# --------------------------------------


def _log(msg):
    line = "%s | %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    print("[backup_upload] " + line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _token():
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(var)
        if v and v.strip():
            return v.strip()
    if os.path.isfile(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as fh:
                v = fh.read().strip()
            if v:
                return v
        except Exception as e:
            _log("读取 %s 失败: %s" % (TOKEN_FILE, e))
    return None


def _api(method, path, token, payload=None, timeout=120):
    url = "https://api.github.com" + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "wpt-auto-backup",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def _blob_sha(data):
    """Git blob 的 SHA-1：sha1(b"blob <len>\\0" + data)"""
    h = hashlib.sha1()
    h.update(b"blob %d\x00" % len(data))
    h.update(data)
    return h.hexdigest()


def _collect_files():
    out = []
    seen = set()
    for pat in BACKUP_PATTERNS:
        for p in sorted(glob.glob(os.path.join(BASE_DIR, pat))):
            if not os.path.isfile(p):
                continue
            rel = os.path.relpath(p, BASE_DIR).replace("\\", "/")
            if rel in EXCLUDE or rel in seen:
                continue
            sz = os.path.getsize(p)
            if sz > MAX_FILE_MB * 1024 * 1024:
                _log("跳过过大文件 %s (%.1f MB)" % (rel, sz / 1048576.0))
                continue
            seen.add(rel)
            out.append((rel, p))
    return out


def run_backup(verbose=True):
    """提交并推送结果文件。返回 True/False，永不抛异常。"""
    t0 = time.time()
    try:
        token = _token()
        if not token:
            _log("未找到令牌：请设置 GH_TOKEN 环境变量，或把令牌写入 %s" % TOKEN_FILE)
            return False

        files = _collect_files()
        if not files:
            _log("没有匹配到要备份的文件")
            return False

        repo = _api("GET", "/repos/%s" % REPO, token)
        branch = repo.get("default_branch") or DEFAULT_BRANCH

        ref = _api("GET", "/repos/%s/git/ref/heads/%s" % (REPO, branch), token)
        parent = ref["object"]["sha"]

        commit = _api("GET", "/repos/%s/git/commits/%s" % (REPO, parent), token)
        base_tree = commit["tree"]["sha"]

        tree = _api("GET", "/repos/%s/git/trees/%s?recursive=1" % (REPO, base_tree), token)
        remote = {e["path"]: e["sha"] for e in tree.get("tree", []) if e.get("type") == "blob"}

        entries = []
        changed = []
        for rel, ap in files:
            with open(ap, "rb") as fh:
                data = fh.read()
            if remote.get(rel) == _blob_sha(data):
                continue
            blob = _api("POST", "/repos/%s/git/blobs" % REPO, token, {
                "content": base64.b64encode(data).decode("ascii"),
                "encoding": "base64",
            })
            entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
            changed.append(rel)

        if not entries:
            if verbose:
                _log("无变化，跳过提交（%d 个文件均为最新）" % len(files))
            return True

        new_tree = _api("POST", "/repos/%s/git/trees" % REPO, token, {
            "base_tree": base_tree,
            "tree": entries,
        })

        msg = "auto backup %s (%d files)" % (time.strftime("%Y-%m-%d %H:%M:%S"), len(entries))
        new_commit = _api("POST", "/repos/%s/git/commits" % REPO, token, {
            "message": msg,
            "tree": new_tree["sha"],
            "parents": [parent],
        })

        _api("PATCH", "/repos/%s/git/refs/heads/%s" % (REPO, branch), token, {
            "sha": new_commit["sha"],
        })

        shown = ", ".join(changed[:8]) + (" ..." if len(changed) > 8 else "")
        _log("已推送 %d 个文件到 %s@%s: %s" % (len(entries), REPO, branch, shown))
        _log("commit %s  (%.1fs)" % (new_commit["sha"][:10], time.time() - t0))
        return True

    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        _log("HTTP %s %s :: %s" % (e.code, e.reason, body))
        if e.code == 401:
            _log(">> 令牌无效或已过期")
        elif e.code == 403:
            _log(">> 权限不足（需要 Contents: Read and write）或触发限流")
        return False
    except Exception as e:
        _log("备份失败: %s %s" % (type(e).__name__, e))
        return False


if __name__ == "__main__":
    ok = run_backup()
    raise SystemExit(0 if ok else 1)
