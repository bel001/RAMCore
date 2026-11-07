@echo off
REM Lanzador RAMCore SIN consola (usa pythonw)
cd /d "%~dp0"
where pythonw >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw "ram_optimizer.py"
) else (
    start "" "C:\Users\Rodrigo\AppData\Local\Python\pythoncore-3.14-64\pythonw.exe" "ram_optimizer.py"
)
