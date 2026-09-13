@echo off
chcp 65001 >nul
title WPT 环境部署 —— 只装环境，不跑仿真
cd /d "%~dp0"

echo ==================================================
echo   WPT 仿真环境部署（仅环境，不启动 AEDT、不跑仿真）
echo ==================================================
echo.

REM ---------- 1) 找 Python ----------
set PY=
where py >nul 2>nul && set PY=py -3
if not defined PY (
  where python >nul 2>nul && set PY=python
)
if not defined PY (
  echo [错误] 没有找到 Python（需要 3.10 或更高）。
  echo   请安装 https://www.python.org/downloads/ ，安装第一屏务必勾选
  echo   [x] Add python.exe to PATH
  echo   装完后重新打开本窗口再双击本文件。
  pause & exit /b 1
)
echo [1/3] Python:
%PY% --version
echo.

REM ---------- 2) 装 pyaedt ----------
echo [2/3] 安装 pyaedt==1.3.0（首次需联网，约 1-2 分钟）...
%PY% -m pip install -q --disable-pip-version-check -U pip
%PY% -m pip install -q --disable-pip-version-check pyaedt==1.3.0
if errorlevel 1 (
  echo [提示] 若上面有红字，多半是网络问题，重新双击本文件再试一次。
  echo.
)
echo.

REM ---------- 3) 只读环境自检（不启动 AEDT） ----------
echo [3/3] 环境自检（只读，不启动 AEDT、不跑仿真，约 5 秒）...
echo --------------------------------------------------
%PY% preflight_2025.py --env-only
echo --------------------------------------------------
echo.
echo ==================================================
echo   期望结果：PASS=4  FAIL=0
echo   报告文件：preflight_report.txt
echo ==================================================
pause
