@echo off
setlocal
cd /d "%~dp0"
title RAMCore - Compilador de Ejecutable (.exe)

echo =======================================================
echo          RAMCore - Compilacion a Ejecutable .EXE
echo =======================================================
echo.

REM 1. Verificar si PyInstaller esta instalado
python -c "import PyInstaller" >nul 2>&1
if %errorlevel% neq 0 (
    echo [i] PyInstaller no esta instalado. Instalando requerimientos...
    python -m pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] No se pudo instalar PyInstaller. Revisa tu conexion a Internet.
        pause
        exit /b 1
    )
)

echo [1/2] Limpiando carpetas previas...
if exist "build" rd /s /q "build"
if exist "dist\RAMCore.exe" del /f /q "dist\RAMCore.exe"

echo [2/2] Compilando con PyInstaller (onefile, windowed)...
python -m PyInstaller ^
    --noconfirm ^
    --onefile ^
    --windowed ^
    --name "RAMCore" ^
    --icon "icono.ico" ^
    --add-data "icono.ico;." ^
    --add-data "icono.png;." ^
    ram_optimizer.py

if %errorlevel% equ 0 (
    echo.
    echo =======================================================
    echo   [OK] Compilacion exitosa!
    echo   Tu ejecutable listo para usar esta en:
    echo   dist\RAMCore.exe
    echo =======================================================
) else (
    echo.
    echo [ERROR] Hubo un error durante la compilacion.
)

echo.
pause
