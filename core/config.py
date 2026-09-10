"""
Gestor de configuración persistente para el complemento meteorológico de ZaraRadio.
Almacena preferencias de usuario en un archivo JSON portable o en AppData.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict


def get_base_directory() -> Path:
    """
    Retorna el directorio base de la aplicación.
    Si se ejecuta como binario congelado (PyInstaller), usa la ubicación del ejecutable.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_config_path() -> Path:
    """
    Determina la ruta óptima para config.json.
    Prioriza la carpeta del ejecutable/proyecto si tiene permisos de escritura.
    Como respaldo, usa %APPDATA%/ZaraWeatherSync.
    """
    base_dir = get_base_directory()
    target = base_dir / "config.json"
    
    # Verificar si es escribible
    try:
        if not target.exists():
            with open(target, "w", encoding="utf-8") as f:
                f.write("{}")
            target.unlink()
        return target
    except (PermissionError, OSError):
        appdata = Path(os.environ.get("APPDATA", str(Path.home())))
        app_dir = appdata / "ZaraWeatherSync"
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir / "config.json"


# Restricciones de la API de Open-Meteo (Fair Use y política de consultas)
MIN_UPDATE_INTERVAL_MINUTES = 15     # Mínimo permitido para evitar sobrecarga y bloqueos de IP
MAX_UPDATE_INTERVAL_MINUTES = 1440   # Máximo permitido (24 horas)

# Valores predeterminados requeridos
DEFAULT_CONFIG: Dict[str, Any] = {
    "output_dir": r"C:\ZaraRadio" if os.path.exists(r"C:\ZaraRadio") else str(get_base_directory()),
    "location_mode": "auto",  # 'auto' (por defecto), 'city' o 'manual'
    "selected_city": "Las Toscas, Santa Fe (Argentina)",
    "manual_lat": -28.351,
    "manual_lon": -59.259,
    "manual_city": "Las Toscas, Santa Fe",
    "temperature_unit": "celsius",  # 'celsius' o 'fahrenheit'
    "autostart": False,
    "minimize_to_tray_on_close": True,
    "update_interval_minutes": 60,
}


def load_config() -> Dict[str, Any]:
    """Carga la configuración desde el archivo JSON fusionándola con los valores por defecto."""
    cfg_path = get_config_path()
    config = DEFAULT_CONFIG.copy()
    
    if cfg_path.exists():
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    config.update(saved)
        except Exception as e:
            print(f"[WARN] Error al leer config.json ({e}). Usando valores por defecto.")
            
    return config


def save_config(config_data: Dict[str, Any]) -> bool:
    """Guarda el diccionario de configuración en el archivo JSON."""
    cfg_path = get_config_path()
    try:
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"[ERROR] No se pudo guardar config.json: {e}")
        return False
