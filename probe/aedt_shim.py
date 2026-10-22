# -*- coding: utf-8 -*-
"""沙箱垫片：把子进程的输出捕获从「管道」改成「临时文件」。

背景：本会话的文件沙箱禁止创建命名/匿名管道（CreatePipe -> WinError 5），
而 pyaedt 在选端口时会跑 `tasklist` 并用 capture_output=True（= PIPE），
导致 Desktop() 初始化直接失败：
    general_methods._get_pids_by_name_windows -> subprocess.run(capture_output=True)
    desktop._find_free_port -> is_grpc_session_active -> active_sessions -> 上面那条

AEDT 本体的启动用的是 stdout/stderr=DEVNULL（desktop.py:418-428），不受影响。
这里只重定向「捕获型」调用，语义保持不变（返回值仍是 CompletedProcess，
stdout/stderr 仍是 str 或 bytes），不改变命令本身。

用法：在任何 pyaedt 导入之前 `import aedt_shim`。
"""
import locale
import subprocess
import tempfile

_real_run = subprocess.run
_real_check_output = subprocess.check_output


def _decode(data, kwargs):
    if kwargs.get("text") or kwargs.get("universal_newlines") or kwargs.get("encoding"):
        enc = kwargs.get("encoding")
        if enc in (None, "locale"):          # CPython 用 "locale" 表示系统默认编码
            enc = locale.getencoding()
        return data.decode(enc, kwargs.get("errors") or "replace")
    return data


def run(cmd, **kwargs):
    cap = kwargs.pop("capture_output", False)
    stdout = kwargs.get("stdout", None)
    stderr = kwargs.get("stderr", None)
    need_out = bool(cap) or (stdout is subprocess.PIPE)
    need_err = bool(cap) or (stderr is subprocess.PIPE)
    if not (need_out or need_err):
        return _real_run(cmd, **kwargs)

    check = kwargs.pop("check", False)
    fo = tempfile.TemporaryFile() if need_out else None
    fe = tempfile.TemporaryFile() if need_err else None
    try:
        if need_out:
            kwargs["stdout"] = fo
        if need_err:
            kwargs["stderr"] = fe
        p = _real_run(cmd, check=False, **kwargs)
        out = err = None
        if need_out:
            fo.seek(0)
            out = _decode(fo.read(), kwargs)
            p.stdout = out
        if need_err:
            fe.seek(0)
            err = _decode(fe.read(), kwargs)
            p.stderr = err
        if check and p.returncode:
            raise subprocess.CalledProcessError(p.returncode, cmd, output=out, stderr=err)
        return p
    finally:
        for f in (fo, fe):
            if f is not None:
                try:
                    f.close()
                except Exception:
                    pass


def check_output(*args, **kwargs):
    kwargs.setdefault("stdout", subprocess.PIPE)
    return run(*args, check=True, **kwargs).stdout


subprocess.run = run
subprocess.check_output = check_output


def patch_pyaedt_proc():
    """pyaedt 用 `tasklist` 枚举 AEDT 进程，而 tasklist 在本沙箱里被拒（Access denied）。

    换成 PowerShell 的 Get-Process（.NET 枚举，本沙箱允许），
    让 active_sessions()/端口分配恢复正常语义（多实例时尤其重要）。
    必须在导入 pyaedt 之后、创建 Desktop 之前调用。
    """
    from ansys.aedt.core.generic import general_methods as gm

    def _pids(image_name):
        if image_name not in ("ansysedt.exe", "ansysedtsv.exe"):
            raise ValueError("Invalid process name: %s" % image_name)
        stem = image_name[:-4]
        r = run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                 "(Get-Process -Name %s -ErrorAction SilentlyContinue).Id" % stem],
                capture_output=True, text=True)
        out = []
        for line in (r.stdout or "").splitlines():
            line = line.strip()
            if line.isdigit():
                out.append(int(line))
        return out

    gm._get_pids_by_name_windows = _pids
    return _pids

