@echo off
chcp 65001 >nul
echo ============================================
echo  WPT 服务器环境检查脚本
echo ============================================
echo.

echo [1/5] 检查 Ansys AEDT ...
where ansysedt >nul 2>&1
if %errorlevel%==0 (
    echo   [OK] AEDT 已安装:
    where ansysedt
) else (
    echo   [MISSING] 未找到 ansysedt，请先安装 AEDT 2024 R1
)
echo.

echo [2/5] 检查 Python ...
where python >nul 2>&1
if %errorlevel%==0 (
    python --version
    echo   [OK] Python 已安装
) else (
    echo   [MISSING] 未找到 python，请安装 Python 3.11
)
echo.

echo [3/5] 检查 pyaedt ...
python -c "import ansys.aedt.core; print('  pyaedt 版本:', __import__('ansys.aedt.core').aedt.core.__version__ if hasattr(__import__('ansys.aedt.core').aedt.core,'__version__') else 'OK')" 2>nul
if %errorlevel%==0 (
    echo   [OK] pyaedt 已安装
) else (
    echo   [MISSING] pyaedt 未安装，执行: pip install pyaedt==1.3.0
)
echo.

echo [4/5] 检查项目文件 ...
if exist "C:\wpt\Projecttonight.aedt" (
    echo   [OK] C:\wpt\Projecttonight.aedt 存在
) else (
    echo   [MISSING] 未找到 C:\wpt\Projecttonight.aedt，请从本机拷入
)
if exist "C:\wpt\batch_sweep.py" (
    echo   [OK] C:\wpt\batch_sweep.py 存在
) else (
    echo   [MISSING] 未找到 batch_sweep.py
)
if exist "C:\wpt\combos.csv" (
    echo   [OK] combos.csv 存在（1331 组合）
) else (
    echo   [MISSING] 未找到 combos.csv，执行: python batch_sweep.py --gen-plan
)
echo.

echo [5/5] 检查 License 环境变量 ...
echo   ANSYSLMD_LICENSE_FILE = %ANSYSLMD_LICENSE_FILE%
if defined ANSYSLMD_LICENSE_FILE (
    echo   [OK] License 变量已设置
) else (
    echo   [CHECK] License 变量未设置，请确认 AEDT license 已激活
)
echo.
echo ============================================
echo  检查完成。红色 [MISSING] 项需处理后再跑。
echo  全部 [OK] 后可执行:
echo    cd C:\wpt
echo    python solve_mag.py        (单点验证)
echo    start /b python batch_sweep.py > batch_run.log 2>&1   (全量扫描)
echo ============================================
pause
