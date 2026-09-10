"""
Sistema de auto-actualización en vivo para ZaraWeatherSync mediante GitHub Releases.
Permite consultar nuevas versiones, descargar el binario y sustituir el ejecutable
en Windows de forma transparente mediante un proceso de transición desacoplado.
"""

import os
import re
import sys
import subprocess
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

import requests

from core.version import __version__, GITHUB_REPO_FULL


def parse_version_tuple(version_str: str) -> Tuple[int, ...]:
    """
    Convierte una cadena de versión tipo 'v1.2.0' o '1.3' en una tupla de enteros (1, 2, 0)
    para permitir comparaciones numéricas precisas.
    """
    cleaned = re.sub(r"[^\d.]", "", str(version_str).strip())
    parts = []
    for part in cleaned.split("."):
        if part.isdigit():
            parts.append(int(part))
        else:
            break
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def check_for_updates(
    current_version: str = __version__,
    repo_full: str = GITHUB_REPO_FULL,
    timeout: int = 8
) -> Dict[str, Any]:
    """
    Consulta la API pública de GitHub Releases para comprobar si existe una versión superior.
    Retorna un diccionario con:
      - 'update_available': bool
      - 'latest_version': str
      - 'current_version': str
      - 'download_url': Optional[str]
      - 'release_notes': str
      - 'html_url': str
      - 'error': Optional[str]
    """
    api_url = f"https://api.github.com/repos/{repo_full}/releases/latest"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": f"ZaraWeatherSync/{current_version}"
    }

    try:
        response = requests.get(api_url, headers=headers, timeout=timeout)

        if response.status_code == 404:
            return {
                "update_available": False,
                "latest_version": current_version,
                "current_version": current_version,
                "download_url": None,
                "release_notes": "",
                "html_url": f"https://github.com/{repo_full}/releases",
                "error": "Aún no se han publicado releases en el repositorio de GitHub."
            }

        response.raise_for_status()
        data = response.json()

        tag_name = data.get("tag_name", "").strip()
        html_url = data.get("html_url", f"https://github.com/{repo_full}/releases")
        release_notes = data.get("body", "Sin notas de versión disponibles.")

        remote_tuple = parse_version_tuple(tag_name)
        local_tuple = parse_version_tuple(current_version)

        # Buscar el ejecutable en los assets del release
        download_url = None
        for asset in data.get("assets", []):
            asset_name = asset.get("name", "").lower()
            if asset_name.endswith(".exe"):
                download_url = asset.get("browser_download_url")
                break

        is_newer = remote_tuple > local_tuple

        return {
            "update_available": is_newer and (download_url is not None or not getattr(sys, "frozen", False)),
            "latest_version": tag_name,
            "current_version": current_version,
            "download_url": download_url,
            "release_notes": release_notes,
            "html_url": html_url,
            "error": None
        }

    except requests.exceptions.Timeout:
        return {
            "update_available": False,
            "latest_version": current_version,
            "current_version": current_version,
            "download_url": None,
            "release_notes": "",
            "html_url": "",
            "error": "Tiempo de espera agotado al consultar actualizaciones en GitHub."
        }
    except requests.exceptions.RequestException as e:
        return {
            "update_available": False,
            "latest_version": current_version,
            "current_version": current_version,
            "download_url": None,
            "release_notes": "",
            "html_url": "",
            "error": f"No se pudo conectar con GitHub: {e}"
        }
    except Exception as e:
        return {
            "update_available": False,
            "latest_version": current_version,
            "current_version": current_version,
            "download_url": None,
            "release_notes": "",
            "html_url": "",
            "error": f"Error inesperado al verificar versión: {e}"
        }


def download_update_file(
    download_url: str,
    progress_callback: Optional[Callable[[float, int, int], None]] = None,
    timeout: int = 30
) -> Tuple[bool, Optional[Path], str]:
    """
    Descarga el archivo ejecutable nuevo en la carpeta temporal de Windows.
    Retorna: (éxito, ruta_temporal, mensaje_error)
    """
    try:
        temp_dir = Path(tempfile.gettempdir())
        target_temp = temp_dir / "ZaraWeatherSync_update.exe"

        # Eliminar archivo temporal previo si quedó de un intento anterior
        if target_temp.exists():
            try:
                target_temp.unlink()
            except Exception:
                pass

        headers = {"User-Agent": f"ZaraWeatherSync/{__version__}"}
        response = requests.get(download_url, headers=headers, stream=True, timeout=timeout)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 65536  # 64 KB

        with open(target_temp, "wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        pct = min(100.0, (downloaded / total_size) * 100.0)
                        progress_callback(pct, downloaded, total_size)

        return True, target_temp, ""

    except Exception as e:
        return False, None, f"Error durante la descarga: {e}"


def apply_update_and_restart(new_exe_path: Path) -> Tuple[bool, str]:
    """
    Reemplaza el ejecutable actual en ejecución por el nuevo archivo descargado
    y reinicia la aplicación automáticamente usando un proceso desacoplado.
    """
    # Si estamos en modo desarrollo (script Python), abrir navegador o avisar
    if not getattr(sys, "frozen", False):
        return False, "La auto-actualización directa solo aplica cuando se ejecuta el archivo .exe compilado."

    current_exe = Path(sys.executable).resolve()
    temp_dir = Path(tempfile.gettempdir())
    script_path = temp_dir / "zara_update_launcher.bat"

    # Script batch que espera a que el proceso anterior finalice, reemplaza el .exe y lo ejecuta
    bat_content = f"""@echo off
chcp 65001 > nul
echo Actualizando ZaraWeatherSync a la ultima version...
timeout /t 1 /nobreak > nul

:retry
move /y "{str(new_exe_path)}" "{str(current_exe)}" > nul 2>&1
if %errorlevel% neq 0 (
    timeout /t 1 /nobreak > nul
    goto retry
)

echo Iniciando nueva version...
start "" "{str(current_exe)}"
del "%~f0"
exit
"""

    try:
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(bat_content)

        # Lanzar el script desacoplado sin ventana visible
        DETACHED_PROCESS = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        subprocess.Popen(
            ["cmd.exe", "/c", str(script_path)],
            creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
            close_fds=True
        )

        return True, "Reiniciando para aplicar la nueva versión..."

    except Exception as e:
        return False, f"No se pudo ejecutar el script de actualización: {e}"
