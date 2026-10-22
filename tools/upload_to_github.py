# -*- coding: utf-8 -*-
r"""把迁移包 + 部分源机文件推到 GitHub 仓库（走 REST API，无需本地 git）。

为什么不用 git
--------------
源机**根本没装 git**（实测 `git --version` 不存在）。项目现有的 `C:\wpt\backup_upload.py`
早已用同一套思路解决过这个问题：Git Data API 建 blob → 建 tree → 建 commit → 移 ref，
**一次产生一个原子提交**，只用 Python 标准库。

设计要点（每条都对应一个真实踩过的坑）
--------------------------------------
1) **逐文件比对远端 blob SHA，无变化不提交** —— 避免空 commit 撑爆历史，
   也与 `backup_upload.py` 的行为一致，不会互相制造噪声。
2) **合并进 base_tree，而不是替换整棵树** —— 仓库里已有 `backup_upload.py` 每小时
   推送的结果 CSV；若整棵树替换，会把那些文件**删掉**。必须基于现有树做增量。
3) **★ `.aedt` 必须显式放行** —— 见本脚本 `GITIGNORE` 常量：
   源机 `C:\wpt\.gitignore` 里有 `*.aedt`，只放行 `!Projecttonight.aedt`；
   而我们的母本工程叫 `Projecttonight_ref.aedt`，**不在放行名单里**。
   照搬那份 .gitignore，上传会"成功"但新设备 clone 下来**没有母本工程** →
   8 个实例在同一秒全部起不来。这是本次上传最高危的一条。
4) **`.gitattributes` 强制二进制** —— 保证跨机 clone 后字节完全一致，
   这样 `verify_pack.py` 的 SHA256 才有意义（否则 git 的换行/编码转换会静默改字节）。
5) **令牌只从环境变量或 `.gh_token` 读，绝不写入任何提交内容**。

用法
----
    set GH_TOKEN=<新令牌>            # 或写进 %USERPROFILE%\.gh_token
    python upload_to_github.py --dry-run
    python upload_to_github.py --apply
    python upload_to_github.py --verify-only

退出码：0=成功 / 1=有阻断项 / 2=脚本自身异常
"""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "sangdoud/wpt-coil-sim"
BRANCH = "master"
TOKEN_CANDIDATES = [
    os.path.join(os.path.expanduser("~"), ".gh_token"),
    r"C:\wpt\.gh_token",
    os.path.join(HERE, ".gh_token"),
]
MAX_FILE_MB = 95           # GitHub 单文件硬限 100 MB，留余量

# ---------------------------------------------------------------------------
# 仓库级 .gitignore —— **必须包含 .aedt 放行规则**（见文件头第 3 条）
# ---------------------------------------------------------------------------
GITIGNORE = """\
# ============================================================================
# 本仓库是 WPT 批量仿真项目的代码/文档/种子仓库
# ⚠️ 关键：.aedt 是**必需资产**（母本工程），不得忽略。
#    源机 C:\\wpt\\.gitignore 里的 `*.aedt` 只放行 !Projecttonight.aedt，
#    会挡住 Projecttonight_ref.aedt —— 那会让新设备 clone 后没有母本工程，
#    整批 8 个实例在同一秒全部起不来。**不要照搬那份 .gitignore。**
# ============================================================================

# ---- 求解产物与锁文件（可再生，一律不入库）----
*.aedtresults/
*.aedt.lock
*.lock
*.auto
*.pyaedt/

# ---- AEDT 工程：默认忽略，但**母本工程必须放行** ----
*.aedt
!Projecttonight_ref.aedt

# ---- 凭据：绝对不许入库 ----
.gh_token
*_token.txt
.env
.env.*

# ---- 日志：一律不入库 ----
# （`upgrade_upload.log` 这类文件里可能出现令牌错误信息与内网路径，实测漏掉
#   `*.log` 会导致 wpt/backup_upload.log 被提交 —— 单一规则比逐条列举更可靠）
*.log

# ---- 运行时产物 ----
__pycache__/
*.pyc
*.tmp
*.bak
*.bak_*
_backup_adapt_*/
_backup_rename_*/

# ---- 批次运行期产物（raw 是真值来源，单独归档，不进代码仓库）----
*_raw_run*.csv
*_plan_shard*.csv
*_worker_run*.json
*_stdout_*.txt

# ---- 大件：安装介质与交付包 ----
*.iso
b1_delivery_*.zip
"""

# ---------------------------------------------------------------------------
# .gitattributes —— 关掉一切自动转换，保证 clone 后字节与源机完全一致，
# 这样 verify_pack.py 的 SHA256 比对才有判据意义。
# ---------------------------------------------------------------------------
GITATTRIBUTES = """\
# 关闭全部自动转换：本项目靠 SHA256 校验迁移完整性（verify_pack.py），
# 任何换行/编码转换都会让校验失去意义。
* -text -diff

# 二进制资产显式声明
*.aedt      binary
*.aedtresults/**  binary
*.iso       binary
*.zip       binary
*.png       binary
*.xlsx      binary
*.docx      binary
"""

# ---------------------------------------------------------------------------
# 要上传的内容：本地路径 -> 仓库内路径
# ---------------------------------------------------------------------------
def build_upload_list(pack, extra_wpt=None):
    items = []   # (本地绝对路径, 仓库相对路径)

    def add_dir(src, dst):
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs
                       if d != "__pycache__" and not d.startswith("_backup_")]
            for fn in sorted(files):
                ap = os.path.join(root, fn)
                rel = os.path.relpath(ap, src).replace("\\", "/")
                items.append((ap, dst.rstrip("/") + "/" + rel))

    def add_file(src, dst):
        items.append((src, dst))

    # ---- 迁移包整体（repo 根 = 迁移包结构）----
    add_dir(os.path.join(pack, "work"), "work")
    add_dir(os.path.join(pack, "wpt"), "wpt")
    add_dir(os.path.join(pack, "probe"), "probe")
    add_dir(os.path.join(pack, "docs"), "docs")
    add_dir(os.path.join(pack, "tools"), "tools")
    for n in ("MANIFEST.json", "交接说明_新设备.md",
              "迁移操作手册.md", "新设备启动提示词.md"):
        add_file(os.path.join(pack, n), n)

    # ---- 生成的两个仓库级配置（内容由本脚本提供，不取本地文件）----
    items.append((None, ".gitignore"))
    items.append((None, ".gitattributes"))

    # ---- 迁移包外的两个说明文档 ----
    mig = os.path.dirname(pack)
    for n in ("README_从哪里开始.md", "新机启动前检查清单_b3.md"):
        p = os.path.join(mig, n)
        if os.path.isfile(p):
            add_file(p, n)

    # ---- 可选：源机代码库 C:\wpt 的入口脚本 ----
    if extra_wpt:
        for n in extra_wpt:
            p = os.path.join(r"C:\wpt", n)
            if os.path.isfile(p):
                add_file(p, "wpt_legacy/" + n)
    return items


GENERATED = {".gitignore": GITIGNORE, ".gitattributes": GITATTRIBUTES}


# ---------------------------------------------------------------------------
def token():
    for var in ("GH_TOKEN", "GITHUB_TOKEN"):
        v = os.environ.get(var)
        if v and v.strip():
            return v.strip(), "环境变量 %s" % var
    for p in TOKEN_CANDIDATES:
        if os.path.isfile(p):
            try:
                v = open(p, encoding="utf-8").read().strip()
                if v:
                    return v, p
            except OSError:
                pass
    return None, None


def api(method, path, tok, payload=None, timeout=180, raw=False):
    """调 GitHub REST API。

    ⚠️ 一律把 HTTPError 转成**带上下文的 RuntimeError**，不让它裸抛。
    踩过的坑：早期版本没接住 HTTPError，空仓库的 409 直接把 traceback 打到
    stderr、退出码变成 2，现场只看到一堆 urllib 栈帧，看不出是哪一步、为什么。
    """
    url = "https://api.github.com" + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={"Authorization": "Bearer " + tok,
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "wpt-migration-uploader",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:300]
        except Exception:                          # noqa: BLE001
            pass
        raise RuntimeError("HTTP %s %s on %s %s :: %s"
                           % (e.code, e.reason, method, path, detail)) from None
    if raw:
        return body
    return json.loads(body.decode("utf-8")) if body else {}


def api_soft(method, path, tok, payload=None, timeout=180):
    """同 api()，但把 HTTP 错误码作为返回值，供"预期可能失败"的探测使用。"""
    try:
        return 200, api(method, path, tok, payload, timeout)
    except RuntimeError as e:
        m = re.match(r"HTTP (\d+)", str(e))
        return (int(m.group(1)) if m else None), str(e)


def git_blob_sha(data):
    """Git blob 的 SHA-1：sha1(b'blob <len>\\0' + data)"""
    h = hashlib.sha1()
    h.update(b"blob %d\x00" % len(data))
    h.update(data)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default=os.path.join(HERE, "pack"))
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--branch", default=BRANCH)
    ap.add_argument("--with-wpt-entry", action="store_true",
                    help="顺带上传 C:\\wpt 的几个入口脚本到 wpt_legacy/")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", help="只清点与比对（默认）")
    g.add_argument("--apply", action="store_true", help="真正提交")
    g.add_argument("--verify-only", action="store_true", help="只查仓库现状与权限")
    args = ap.parse_args()

    print("=" * 78)
    print("迁移包 → GitHub 上传器")
    print("  仓库 %s@%s" % (args.repo, args.branch))
    print("  时间 %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 78, flush=True)

    # ---- 1) 令牌 ----
    tok, src = token()
    if not tok:
        print("\n[FAIL] 找不到令牌。请二选一：")
        print("   · 设置环境变量：  $env:GH_TOKEN = '<新令牌>'")
        print("   · 写入文件：      %s" % TOKEN_CANDIDATES[0])
        print("   需要的权限（细粒度 PAT）：Repository access 只选 %s；"
              "Permissions → Contents = Read and write" % args.repo)
        return 1
    print("\n令牌来源：%s（长度 %d，不显示内容）" % (src, len(tok)))

    # ---- 2) 仓库与权限 ----
    try:
        repo = api("GET", "/repos/%s" % args.repo, tok)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        print("\n[FAIL] 无法访问仓库 %s：HTTP %s %s\n       %s" % (args.repo, e.code, e.reason, body))
        if e.code == 401:
            print("       → 令牌无效/已过期。这正是当前的状态（实测 401 Bad credentials），"
                  "请重新生成一个 PAT。")
        elif e.code == 404:
            print("       → 仓库不存在，或令牌没有该仓库的访问权（私有仓库对无权者返回 404）。")
        return 1
    print("仓库      : %s" % repo["full_name"])
    print("可见性    : %s" % ("private" if repo["private"] else "public"))
    print("默认分支  : %s" % repo["default_branch"])
    print("仓库体积  : %.1f MB" % (repo["size"] / 1024.0))
    print("推送权限  : %s" % (repo.get("permissions", {}).get("push")))

    br = args.branch or repo["default_branch"]
    # ⚠️ 判"空仓库"**不能看 repo["size"]**。实测踩到：刚推完引导提交后，
    #    `GET /repos/...` 的 size 字段仍是 0（GitHub 侧异步统计），于是重跑时
    #    又误判成空仓库 —— 结果建了一棵**无 base_tree 的树**，差点把已有提交顶掉，
    #    而且最后一步 POST ref 撞 422 "Reference already exists"。
    #    正确判据只有一个：**目标分支是否存在**。
    #    · 分支存在（含空仓库先落过引导提交的情况）-> 有 parent、有 base_tree，走 PATCH
    #    · 分支不存在                            -> 真空仓库，走 POST 建 ref
    #    注意坑：空仓库下 GET /git/ref/heads/<br> 返回的是 **409**（"Git Repository is empty."），
    #    不是 404。
    code, res = api_soft("GET", "/repos/%s/git/ref/heads/%s" % (args.repo, br), tok)
    if code == 200 and isinstance(res, dict) and res.get("object", {}).get("sha"):
        is_empty = False
        parent = res["object"]["sha"]
    elif code in (404, 409):
        is_empty = True
        parent = base_tree = None
    else:
        print("\n[FAIL] 取分支 %s 失败：%s" % (br, res))
        return 1

    if is_empty:
        print("仓库状态  : 分支 %s 不存在 -> **真空仓库**（首次提交）" % br)
        remote = {}
    else:
        commit = api("GET", "/repos/%s/git/commits/%s" % (args.repo, parent), tok)
        base_tree = commit["tree"]["sha"]
        tree = api("GET", "/repos/%s/git/trees/%s?recursive=1"
                   % (args.repo, base_tree), tok)
        remote = {e["path"]: e for e in tree.get("tree", []) if e.get("type") == "blob"}
        print("分支 %s  : 已存在，HEAD=%s（%d 个文件）"
              % (br, parent[:10], len(remote)))

    if args.verify_only:
        print("\n[OK] 仓库可访问、令牌有效、分支可读。退出码 0")
        return 0

    # ---- 3) 清点本地 ----
    extra = None
    if args.with_wpt_entry:
        extra = ["batch_sweep_lc.py", "coil_gen.py", "wpt_contract.py",
                 "coil_template_Rx.json"]
    items = build_upload_list(os.path.abspath(args.pack), extra)

    print("\n待上传清单：%d 项" % len(items))
    by_top = {}
    for ap_, rel in items:
        top = rel.split("/", 1)[0]
        by_top.setdefault(top, [0, 0])
        by_top[top][0] += 1
        if ap_ and os.path.isfile(ap_):
            by_top[top][1] += os.path.getsize(ap_)
        elif ap_ is None:
            by_top[top][1] += len(GENERATED.get(rel, "").encode("utf-8"))
    for k in sorted(by_top):
        n, b = by_top[k]
        print("   %-18s %4d 文件  %8.2f MB" % (k, n, b / 1048576.0))

    # ---- 4) 逐文件比对 ----
    to_push, unchanged, missing, toobig = [], [], [], []
    for ap_, rel in items:
        if ap_ is None:
            data = GENERATED[rel].encode("utf-8")
        else:
            if not os.path.isfile(ap_):
                missing.append(rel)
                continue
            if os.path.getsize(ap_) > MAX_FILE_MB * 1048576:
                toobig.append((rel, os.path.getsize(ap_) / 1048576.0))
                continue
            data = open(ap_, "rb").read()
        sha = git_blob_sha(data)
        if remote.get(rel, {}).get("sha") == sha:
            unchanged.append(rel)
        else:
            to_push.append((ap_, rel, data, sha))

    print("\n比对结果：")
    print("   需上传 %d" % len(to_push))
    print("   已是最新 %d" % len(unchanged))
    if missing:
        print("   [FAIL] 本地缺失 %d 项：%s" % (len(missing), "、".join(missing[:6])))
    if toobig:
        print("   [FAIL] 超过 %d MB 上限：" % MAX_FILE_MB)
        for r, mb in toobig:
            print("       %.1f MB  %s" % (mb, r))
    # 关键文件必须在内（★ .aedt 陷阱的显式判据）
    ref_rel = "work/Projecttonight_ref.aedt"
    in_list = any(r == ref_rel for _, r, _, _ in to_push) or ref_rel in unchanged
    if not in_list:
        print("\n[FAIL] ★ 母本工程 %s **不在上传清单里**！" % ref_rel)
        print("       这正是 `*.aedt` 被 .gitignore 挡住的后果 —— 新设备 clone 后将无法启动批次。")
        return 1
    print("   [OK] ★ 母本工程在清单内：%s（%.2f MB）"
          % (ref_rel, os.path.getsize(os.path.join(args.pack, ref_rel)) / 1048576.0))

    if missing or toobig:
        print("\n退出码 1 —— 先消掉上面的 FAIL。")
        return 1

    if not args.apply:
        print("\n[预演] 未提交。确认无误后加 --apply。")
        for _, r, d, _s in to_push[:15]:
            print("   · %-52s %8.1f KB" % (r, len(d) / 1024.0))
        if len(to_push) > 15:
            print("   ... 另有 %d 项" % (len(to_push) - 15))
        print("\n退出码 0")
        return 0

    # ---- 5) 上传 blob ----
    print("\n上传 blob（逐个，失败即停，不做宽泛 except）...")
    entries, nodata = [], []
    t0 = time.time()
    for i, (ap_, rel, data, sha) in enumerate(to_push, 1):
        try:
            blob = api("POST", "/repos/%s/git/blobs" % args.repo, tok, {
                "content": base64.b64encode(data).decode("ascii"),
                "encoding": "base64"})
            entries.append({"path": rel, "mode": "100644",
                            "type": "blob", "sha": blob["sha"]})
            if i % 25 == 0 or i == len(to_push):
                print("   %d/%d  (%.0fs)" % (i, len(to_push), time.time() - t0), flush=True)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:200]
            print("   [FAIL] %s : HTTP %s %s %s" % (rel, e.code, e.reason, body))
            return 1

    # ---- 6) 建 tree / commit / 移 ref ----
    if is_empty:
        print("\n建 tree（**首次提交**：无 base_tree，直接以本次文件构成整棵树）...")
        new_tree = api("POST", "/repos/%s/git/trees" % args.repo, tok, {"tree": entries})
    else:
        print("\n建 tree（base_tree 合并，**不删除远端已有文件**）...")
        new_tree = api("POST", "/repos/%s/git/trees" % args.repo, tok,
                       {"base_tree": base_tree, "tree": entries})
    msg = ("migration pack: %d files, seed project + b3 batch framework + tools + docs\n\n"
           "源机迁移包整体入库（新设备据此 clone 即可）。\n"
           "含母本工程 Projecttonight_ref.aedt（已显式放行，绕过 *.aedt 忽略规则）。\n"
           "%.1f MB / %d 文件。" % (len(entries),
                                   sum(len(d) for _, _, d, _ in to_push) / 1048576.0,
                                   len(entries)))
    print("建 commit ...")
    cpayload = {"message": msg, "tree": new_tree["sha"]}
    if parent:
        cpayload["parents"] = [parent]        # 首次提交时不能带空的 parents
    new_commit = api("POST", "/repos/%s/git/commits" % args.repo, tok, cpayload)

    if is_empty:
        # ⚠️ "空仓库"有两种子情形，必须分开处理（实测踩到）：
        #   (a) 真的什么都没有 -> POST /git/refs 新建分支
        #   (b) 检测时 size==0、但在我们上传 blob 的这几分钟里**别人（或我们自己）
        #       已经用 Contents API 落了引导提交** -> 分支已存在 -> POST 会 422
        #       "Reference already exists"，正确动作是 PATCH。
        #   实测经历：先推 .gitignore 做引导提交破解 409，252 个 blob 传完后
        #   才在最后一步撞上 422，白白多花 196 秒重传。故此处按 422 回退到 PATCH。
        code, res = api_soft("POST", "/repos/%s/git/refs" % args.repo, tok,
                             {"ref": "refs/heads/%s" % br, "sha": new_commit["sha"]})
        if code == 201:
            print("   已新建 ref heads/%s" % br)
        elif code == 422:
            print("   分支已存在（引导提交创建过），改为 PATCH 更新 ...")
            api("PATCH", "/repos/%s/git/refs/heads/%s" % (args.repo, br), tok,
                {"sha": new_commit["sha"], "force": False})
        else:
            print("\n[FAIL] 创建 ref 失败：%s" % res)
            return 1
        if repo.get("default_branch") != br:
            api("PATCH", "/repos/%s" % args.repo, tok, {"default_branch": br})
            print("   已把默认分支设为 %s" % br)
    else:
        print("移动 ref %s ..." % br)
        api("PATCH", "/repos/%s/git/refs/heads/%s" % (args.repo, br), tok,
            {"sha": new_commit["sha"]})

    print("\n[OK] 已推送 %d 个文件到 %s@%s" % (len(entries), args.repo, br))
    print("     commit %s" % new_commit["sha"])
    print("     耗时 %.1fs" % (time.time() - t0))
    print("\n下一步（新设备）：")
    print("   git clone https://github.com/%s.git wpt_mig" % args.repo)
    print("   cd wpt_mig && %s tools/verify_pack.py --pack ." % "python")
    print("退出码 0")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:                      # noqa: BLE001
        print("\n[FAIL] upload_to_github 自身异常：%r" % (exc,), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)
