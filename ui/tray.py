"""
Integración con el área de notificación (System Tray) de Windows usando pystray.
Permite ejecutar el complemento en segundo plano sin estorbar la transmisión radial.
"""

import threading
from pathlib import Path
from typing import Callable, Optional
from PIL import Image, ImageDraw


def generate_fallback_icon() -> Image.Image:
    """Genera una imagen en memoria para el icono de la bandeja si no existe archivo .ico."""
    size = 64
    img = Image.new("RGBA", (size, size), (15, 23, 42, 255))
    draw = ImageDraw.Draw(img)
    # Sol
    draw.ellipse([32, 10, 54, 32], fill=(245, 158, 11, 255))
    # Nube
    draw.rounded_rectangle([10, 26, 54, 50], radius=10, fill=(241, 245, 249, 255))
    draw.ellipse([18, 18, 38, 40], fill=(241, 245, 249, 255))
    return img


class SystemTrayManager:
    def __init__(
        self,
        icon_path: Optional[Path],
        on_show: Callable[[], None],
        on_refresh: Callable[[], None],
        on_exit: Callable[[], None],
    ):
        self.icon_path = icon_path
        self.on_show = on_show
        self.on_refresh = on_refresh
        self.on_exit = on_exit
        self.icon: Optional[object] = None
        self._thread: Optional[threading.Thread] = None

    def _get_image(self) -> Image.Image:
        if self.icon_path and self.icon_path.exists():
            try:
                return Image.open(self.icon_path)
            except Exception as e:
                print(f"[WARN] Error cargando icono ({e}), usando fallback.")
        return generate_fallback_icon()

    def _create_menu(self):
        import pystray
        return pystray.Menu(
            pystray.MenuItem("Abrir Ventana", lambda icon, item: self.on_show(), default=True),
            pystray.MenuItem("Actualizar Clima Ahora", lambda icon, item: self.on_refresh()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Salir de ZaraWeatherSync", lambda icon, item: self.on_exit()),
        )

    def start(self):
        """Inicia el icono de la bandeja del sistema en un hilo secundario."""
        try:
            import pystray
            image = self._get_image()
            menu = self._create_menu()
            self.icon = pystray.Icon(
                "ZaraWeatherSync",
                image,
                "ZaraWeatherSync - Complemento ZaraRadio",
                menu
            )
            self._thread = threading.Thread(target=self.icon.run, daemon=True)
            self._thread.start()
        except ImportError:
            print("[WARN] pystray no está instalado. Operación en segundo plano limitada.")
        except Exception as e:
            print(f"[ERROR] No se pudo inicializar la bandeja del sistema: {e}")

    def notify(self, title: str, message: str):
        """Muestra una notificación en la bandeja si el sistema lo soporta."""
        if self.icon and hasattr(self.icon, "notify"):
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def stop(self):
        """Detiene y elimina el icono de la bandeja."""
        if self.icon:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None
