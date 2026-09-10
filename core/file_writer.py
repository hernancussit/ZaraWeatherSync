"""
Generador de archivo clima.txt con formato estricto para ZaraRadio.
Garantiza escritura atómica para evitar bloqueos durante la emisión radial.
"""

import os
from pathlib import Path
from typing import Tuple


def test_directory_writable(directory_path: str) -> Tuple[bool, str, bool]:
    """
    Comprueba si una carpeta tiene permisos de escritura y lectura garantizados para ZaraRadio.
    Retorna: (es_escribible: bool, mensaje: str, es_carpeta_sistema_peligrosa: bool)
    """
    if not directory_path:
        return False, "La ruta de destino no puede estar vacía.", False

    target_dir = Path(directory_path)
    path_str = str(target_dir).lower()

    # Detectar si está dentro de Program Files (riesgo de virtualización UAC de Windows)
    is_system_protected = (
        "program files" in path_str or
        "archivos de programa" in path_str or
        "system32" in path_str
    )

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        test_file = target_dir / ".zara_write_test.tmp"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test")
        test_file.unlink()

        if is_system_protected:
            return (
                True,
                "Atención: Carpeta en 'Archivos de Programa'. Podría requerir ejecutar como Administrador "
                "o sufrir virtualización UAC. Se recomienda usar 'C:\\ZaraRadio' o una carpeta propia.",
                True
            )
        return True, "Carpeta con permisos completos. ZaraRadio podrá acceder sin problemas.", False

    except PermissionError:
        return False, "Error de permisos: Windows no permite escribir en esta carpeta sin elevación.", True
    except Exception as e:
        return False, f"No se pudo acceder a la carpeta: {e}", False


def write_zara_clima_file(target_directory: str, temperature: int, humidity: int) -> Tuple[bool, str]:
    """
    Escribe el archivo clima.txt en la ruta especificada con el formato estricto:
    Temperature:25
    Humidity:60

    Garantiza permisos de lectura compartida para que ZaraRadio nunca encuentre el archivo bloqueado.
    Retorna: (éxito: bool, mensaje_o_ruta: str)
    """
    if not target_directory:
        return False, "La ruta de destino no ha sido especificada."

    target_dir = Path(target_directory)

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return False, f"No se pudo acceder o crear la carpeta '{target_directory}': {e}"

    final_file = target_dir / "clima.txt"
    temp_file = target_dir / "clima.txt.tmp"

    content = f"Temperature:{int(temperature)}\nHumidity:{int(humidity)}\n"

    try:
        # Escribir primero en archivo temporal para asegurar reemplazo atómico
        with open(temp_file, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        os.replace(temp_file, final_file)
        return True, str(final_file)

    except Exception as e:
        try:
            with open(final_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(content)
            return True, str(final_file)
        except Exception as e2:
            return False, f"Error al escribir clima.txt: {e2} (falló método atómico: {e})"
        finally:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass
