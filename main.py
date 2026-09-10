"""
Punto de entrada principal para ZaraWeatherSync.
Controla argumentos de línea de comandos, instancia única en Windows e inicialización de la UI.
"""

import sys
import ctypes
from pathlib import Path

# Ajuste de DPI Awareness en Windows para gráficos nítidos sin distorsión
if sys.platform.startswith("win"):
    try:
        # 1 = PROCESS_SYSTEM_DPI_AWARE (Óptimo para CustomTkinter en monitores con zoom 125%/150%)
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from ui.app import ZaraWeatherApp


def single_instance_guard():
    """
    Evita ejecutar múltiples instancias simultáneas en Windows usando un Mutex nombrado.
    Si ya hay otra instancia corriendo, finaliza silenciosamente.
    """
    if not sys.platform.startswith("win"):
        return None

    try:
        import win32event
        import win32api
        import winerror
        mutex = win32event.CreateMutex(None, False, "Global\\ZaraWeatherSync_SingleInstance_Mutex")
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            print("[INFO] Otra instancia de ZaraWeatherSync ya se encuentra en ejecución.")
            sys.exit(0)
        return mutex
    except ImportError:
        # Respaldo simple sin pywin32 mediante ctypes
        try:
            mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Global\\ZaraWeatherSync_SingleInstance_Mutex")
            last_error = ctypes.windll.kernel32.GetLastError()
            ERROR_ALREADY_EXISTS = 183
            if last_error == ERROR_ALREADY_EXISTS:
                print("[INFO] Otra instancia de ZaraWeatherSync ya se encuentra en ejecución.")
                sys.exit(0)
            return mutex
        except Exception:
            return None


def main():
    # Garantizar instancia única
    _mutex = single_instance_guard()

    # Verificar argumentos (ej: --tray para arranque silencioso desde Windows Run)
    start_in_tray = "--tray" in sys.argv or "--minimized" in sys.argv

    # Inicializar aplicación
    app = ZaraWeatherApp(start_in_tray=start_in_tray)
    app.mainloop()


if __name__ == "__main__":
    main()
