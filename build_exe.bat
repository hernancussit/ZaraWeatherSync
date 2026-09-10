@echo off
chcp 65001 > nul
echo ======================================================================
echo    Compilador Automatizado de ZaraWeatherSync (.exe independiente)
echo ======================================================================
echo.

:: 1. Verificar si Python está disponible
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] No se encontró 'python' en el PATH del sistema.
    echo Por favor asegúrese de tener Python 3.10 o superior instalado y agregado al PATH.
    pause
    exit /b 1
)

:: 2. Crear entorno virtual si no existe
if not exist "venv" (
    echo [1/4] Creando entorno virtual 'venv'...
    python -m venv venv
    if %ERRORLEVEL% NEQ 0 (
        echo [ERROR] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

:: 3. Instalar dependencias
echo [2/4] Instalando dependencias desde requirements.txt...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Ocurrió un error al instalar las dependencias.
    pause
    exit /b 1
)

:: 4. Generar iconos de la aplicación
echo [3/4] Generando iconos de alta resolución...
python assets\make_icon.py

:: 5. Compilar con PyInstaller en un solo ejecutable sin consola
echo [4/4] Compilando con PyInstaller (onefile, sin consola, icono incrustado)...
pyinstaller --noconsole ^
            --onefile ^
            --clean ^
            --name "ZaraWeatherSync" ^
            --icon "assets\icon.ico" ^
            --collect-all "customtkinter" ^
            --add-data "assets;assets" ^
            main.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================================================
    echo   ¡Compilación exitosa!
    echo   El archivo ejecutable se encuentra en:
    echo   dist\ZaraWeatherSync.exe
    echo ======================================================================
) else (
    echo.
    echo [ERROR] La compilación con PyInstaller ha fallado. Revise los mensajes arriba.
)

pause
