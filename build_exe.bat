@echo off
chcp 65001 > nul
echo ======================================================================
echo    Compilador Automatizado de ZaraWeatherSync (.exe independiente)
echo ======================================================================
echo(

REM 1. Detectar comando de Python
set "PYTHON_CMD="
if exist "venv\Scripts\python.exe" set "PYTHON_CMD=venv\Scripts\python.exe"
if "%PYTHON_CMD%"=="" (
    where python >nul 2>&1
    if %ERRORLEVEL% EQU 0 set "PYTHON_CMD=python"
)
if "%PYTHON_CMD%"=="" if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)

if "%PYTHON_CMD%"=="" (
    echo [ERROR] No se encontro Python en el equipo ni en el entorno virtual.
    echo Por favor asegurese de tener Python 3.10 o superior instalado.
    if "%~1"=="" pause
    exit /b 1
)

REM 2. Crear entorno virtual si no existe
if not exist "venv" (
    echo [1/4] Creando entorno virtual 'venv'...
    "%PYTHON_CMD%" -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        if "%~1"=="" pause
        exit /b 1
    )
)

REM 3. Instalar dependencias
echo [2/4] Instalando dependencias desde requirements.txt...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Ocurrio un error al instalar las dependencias.
    if "%~1"=="" pause
    exit /b 1
)

REM 4. Generar iconos de la aplicacion
echo [3/4] Generando iconos de alta resolucion...
python assets\make_icon.py

REM 5. Compilar con PyInstaller en un solo ejecutable sin consola
echo [4/4] Compilando con PyInstaller [onefile, sin consola, icono incrustado]...
pyinstaller --noconsole ^
            --onefile ^
            --clean ^
            --name "ZaraWeatherSync" ^
            --icon "assets\icon.ico" ^
            --collect-all "customtkinter" ^
            --add-data "assets;assets" ^
            main.py

if %ERRORLEVEL% EQU 0 (
    echo(
    echo ======================================================================
    echo   Compilacion exitosa!
    echo   El archivo ejecutable se encuentra en:
    echo   dist\ZaraWeatherSync.exe
    echo ======================================================================
) else (
    echo(
    echo [ERROR] La compilacion con PyInstaller ha fallado. Revise los mensajes arriba.
)

if "%~1"=="" pause
