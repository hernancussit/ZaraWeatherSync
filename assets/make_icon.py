"""
Generador de iconos (.ico y .png) para ZaraWeatherSync.
Crea un icono moderno con sol y nube estilizados usando Pillow.
"""

from pathlib import Path
from PIL import Image, ImageDraw


def create_weather_icon(output_dir: Path) -> Path:
    """Genera icon.ico y icon.png con múltiples resoluciones para Windows."""
    output_dir.mkdir(parents=True, exist_ok=True)
    ico_path = output_dir / "icon.ico"
    png_path = output_dir / "icon.png"

    # Generar en resolución alta (256x256) con antialiasing
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Fondo circular con gradiente o color de acento moderno (Azul profundo / Cian oscuro)
    draw.rounded_rectangle([8, 8, size - 8, size - 8], radius=54, fill=(15, 23, 42, 255), outline=(56, 189, 248, 200), width=6)

    # 2. Sol brillante (Dorado / Naranja) en la esquina superior derecha
    sun_bbox = [110, 40, 200, 130]
    draw.ellipse(sun_bbox, fill=(245, 158, 11, 255), outline=(251, 191, 36, 255), width=4)

    # Rayos de sol sutiles
    rays = [
        [(155, 20), (155, 34)],
        [(155, 136), (155, 150)],
        [(90, 85), (104, 85)],
        [(206, 85), (220, 85)],
        [(110, 40), (120, 50)],
        [(190, 120), (200, 130)],
        [(110, 130), (120, 120)],
        [(190, 50), (200, 40)],
    ]
    for start, end in rays:
        draw.line([start, end], fill=(251, 191, 36, 220), width=5)

    # 3. Nube estilizada en primer plano (Blanco y cian suave)
    # Círculos que forman la nube
    cloud_fill = (241, 245, 249, 255)
    cloud_border = (203, 213, 225, 255)
    
    # Base redondeada de la nube
    draw.rounded_rectangle([44, 120, 212, 195], radius=36, fill=cloud_fill, outline=cloud_border, width=4)
    # Lóbulo superior izquierdo
    draw.ellipse([70, 95, 145, 170], fill=cloud_fill, outline=cloud_border, width=4)
    # Lóbulo superior derecho
    draw.ellipse([125, 105, 185, 165], fill=cloud_fill, outline=cloud_border, width=4)
    # Redibujar relleno interno para cubrir bordes intersectados
    draw.rounded_rectangle([48, 124, 208, 191], radius=32, fill=cloud_fill)
    draw.ellipse([74, 99, 141, 166], fill=cloud_fill)
    draw.ellipse([129, 109, 181, 161], fill=cloud_fill)

    # 4. Gotas de lluvia o detalle de humedad en la base
    drop_color = (56, 189, 248, 255)
    draw.ellipse([80, 205, 92, 225], fill=drop_color)
    draw.ellipse([125, 205, 137, 225], fill=drop_color)
    draw.ellipse([170, 205, 182, 225], fill=drop_color)

    # Guardar PNG en alta resolución
    img.save(png_path, "PNG")

    # Guardar .ICO en múltiples resoluciones estándar de Windows (16, 32, 48, 64, 128, 256)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ico_path, format="ICO", sizes=sizes)

    return ico_path


if __name__ == "__main__":
    assets_dir = Path(__file__).resolve().parent
    created = create_weather_icon(assets_dir)
    print(f"Icono creado con éxito en: {created}")
