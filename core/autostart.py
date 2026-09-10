"""
Gestor de inicio automático en Windows mediante el Registro (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run).
Permite que el complemento meteorológico inicie silenciosamente con el sistema operativo.
"""

import os
import sys
from pathlib import Path
from typing import Tuple

APP_REG_NAME = "ZaraWeatherSync"
RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_windows() -> bool:
    """Verifica si el sistema operativo actual es Windows."""
    return sys.platform.startswith("win")


def get_startup_command() -> str:
    """
    Retorna el comando exacto para iniciar la aplicación.
    Si está compilado con PyInstaller, usa la ruta del .exe.
    Si se ejecuta como script Python, usa pythonw.exe con el script principal.
    """
    if getattr(sys, "frozen", False):
        # Ejecutable compilado (.exe)
        exe_path = Path(sys.executable).resolve()
        return f'"{exe_path}" --tray'
    else:
        # Modo desarrollo / script Python
        python_dir = Path(sys.executable).parent
        pythonw_path = python_dir / "pythonw.exe"
        if not pythonw_path.exists():
            pythonw_path = Path(sys.executable)
        
        main_script = Path(__file__).resolve().parent.parent / "main.py"
        return f'"{pythonw_path}" "{main_script}" --tray'


def is_autostart_enabled(app_name: str = APP_REG_NAME) -> bool:
    """Comprueba si la entrada de inicio automático existe en el Registro."""
    if not is_windows():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
            try:
                winreg.QueryValueEx(key, app_name)
                return True
            except FileNotFoundError:
                return False
    except Exception as e:
        print(f"[DEBUG] Error al leer el registro de inicio: {e}")
        return False


def set_autostart(enable: bool, app_name: str = APP_REG_NAME) -> Tuple[bool, str]:
    """
    Habilita o deshabilita la ejecución automática al inicio de Windows.
    Retorna: (éxito: bool, mensaje: str)
    """
    if not is_windows():
        return False, "La función de inicio automático solo está disponible en Windows."

    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_ALL_ACCESS) as key:
            if enable:
                cmd = get_startup_command()
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                return True, "Inicio automático habilitado exitosamente en el Registro."
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    return True, "Inicio automático deshabilitado exitosamente."
                except FileNotFoundError:
                    return True, "La entrada no existía en el Registro."
    except PermissionError:
        return False, "Permisos insuficientes para modificar el Registro."
    except Exception as e:
        return False, f"Error al modificar el Registro de Windows: {e}"
