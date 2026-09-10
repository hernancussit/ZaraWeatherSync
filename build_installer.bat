@echo off
chcp 65001 > nul
echo ======================================================================
echo    Generador de Instalador de ZaraWeatherSync (Setup Wizard)
echo ======================================================================
echo(

REM 1. Verificar si existe el ejecutable compilado
if not exist "dist\ZaraWeatherSync.exe" (
    echo [AVISO] No se encontro 'dist\ZaraWeatherSync.exe'.
    echo Compilando primero el ejecutable con PyInstaller...
    call build_exe.bat --nopause
    if not exist "dist\ZaraWeatherSync.exe" (
        echo [ERROR] No se pudo generar 'dist\ZaraWeatherSync.exe'. Abortando.
        if "%~1"=="" pause
        exit /b 1
    )
)

REM 2. Localizar el compilador ISCC.exe de Inno Setup
set "ISCC_PATH="
if exist "%LOCALAPPDATA%\Programs\InnoSetup6\ISCC.exe" set "ISCC_PATH=%LOCALAPPDATA%\Programs\InnoSetup6\ISCC.exe"
if "%ISCC_PATH%"=="" if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if "%ISCC_PATH%"=="" if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC_PATH=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if "%ISCC_PATH%"=="" (
    where ISCC.exe >nul 2>&1
    if %ERRORLEVEL% EQU 0 set "ISCC_PATH=ISCC.exe"
)

if "%ISCC_PATH%"=="" (
    echo [ERROR] No se encontro el compilador de Inno Setup ISCC.exe.
    echo Por favor asegurese de tener Inno Setup 6 instalado en el equipo.
    echo Descarga: https://jrsoftware.org/isdl.php
    if "%~1"=="" pause
    exit /b 1
)

echo [1/2] Compilador Inno Setup detectado en:
echo       "%ISCC_PATH%"
echo(
echo [2/2] Compilando asistente de instalacion 'ZaraWeatherSync_Setup.exe'...
"%ISCC_PATH%" "installer\setup.iss"

if %ERRORLEVEL% EQU 0 (
    echo(
    echo ======================================================================
    echo   Instalador generado con exito!
    echo   Ubicacion: dist\ZaraWeatherSync_Setup.exe
    echo ======================================================================
) else (
    echo(
    echo [ERROR] Ocurrio un error al compilar el instalador con Inno Setup.
)

if "%~1"=="" pause
