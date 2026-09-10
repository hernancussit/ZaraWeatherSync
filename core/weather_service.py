"""
Servicio de obtención de datos meteorológicos y geolocalización.
Utiliza Open-Meteo (sin necesidad de API Key) y geolocalización por IP.
"""

from typing import Dict, Optional, Tuple
import requests


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
IP_GEOLOCATION_URL = "http://ip-api.com/json"
IP_GEOLOCATION_FALLBACK = "https://ipapi.co/json/"


def get_ip_location(timeout: int = 8) -> Tuple[bool, float, float, str]:
    """
    Obtiene las coordenadas geográficas aproximadas basadas en la IP pública.
    Retorna: (éxito, latitud, longitud, nombre_ubicacion)
    """
    # Intento 1: ip-api.com
    try:
        resp = requests.get(IP_GEOLOCATION_URL, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "success":
                lat = float(data.get("lat", 0.0))
                lon = float(data.get("lon", 0.0))
                city = data.get("city", "")
                region = data.get("regionName", "")
                country = data.get("country", "")
                location_name = f"{city}, {region} ({country})".strip(", ()")
                return True, lat, lon, location_name
    except Exception as e:
        print(f"[DEBUG] Error con ip-api.com: {e}")

    # Intento 2: ipapi.co (fallback)
    try:
        resp = requests.get(IP_GEOLOCATION_FALLBACK, timeout=timeout, headers={"User-Agent": "ZaraWeatherSync/1.0"})
        if resp.status_code == 200:
            data = resp.json()
            lat = float(data.get("latitude", 0.0))
            lon = float(data.get("longitude", 0.0))
            city = data.get("city", "")
            region = data.get("region", "")
            country = data.get("country_name", "")
            location_name = f"{city}, {region} ({country})".strip(", ()")
            return True, lat, lon, location_name
    except Exception as e:
        print(f"[DEBUG] Error con ipapi.co fallback: {e}")

    return False, 0.0, 0.0, "Ubicación desconocida (Fallo de red)"


def fetch_weather(lat: float, lon: float, temperature_unit: str = "celsius", timeout: int = 10) -> Dict[str, Optional[int]]:
    """
    Consulta Open-Meteo para obtener temperatura y humedad relativa actuales.
    Retorna un diccionario con:
      - 'success': bool
      - 'temperature': int (redondeado a entero)
      - 'humidity': int (redondeado a entero)
      - 'unit': str ('°C' o '°F')
      - 'error': str (mensaje en caso de fallo)
    """
    unit_param = "fahrenheit" if str(temperature_unit).lower() == "fahrenheit" else "celsius"
    params = {
        "latitude": round(lat, 4),
        "longitude": round(lon, 4),
        "current": "temperature_2m,relative_humidity_2m",
        "temperature_unit": unit_param,
        "timezone": "auto"
    }

    try:
        response = requests.get(OPEN_METEO_URL, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        current = data.get("current")
        if not current:
            return {
                "success": False,
                "temperature": None,
                "humidity": None,
                "error": "La API no devolvió datos actuales ('current')."
            }

        temp_raw = current.get("temperature_2m")
        humidity_raw = current.get("relative_humidity_2m")

        if temp_raw is None or humidity_raw is None:
            return {
                "success": False,
                "temperature": None,
                "humidity": None,
                "error": "Valores de temperatura o humedad no encontrados en la respuesta."
            }

        # Redondeo estricto a números enteros
        temp_int = int(round(float(temp_raw)))
        humidity_int = int(round(float(humidity_raw)))

        return {
            "success": True,
            "temperature": temp_int,
            "humidity": humidity_int,
            "unit": "°F" if unit_param == "fahrenheit" else "°C",
            "error": None
        }

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "temperature": None,
            "humidity": None,
            "error": "Tiempo de espera agotado al conectar con Open-Meteo."
        }
    except requests.exceptions.RequestException as e:
        return {
            "success": False,
            "temperature": None,
            "humidity": None,
            "error": f"Error de red: {e}"
        }
    except Exception as e:
        return {
            "success": False,
            "temperature": None,
            "humidity": None,
            "error": f"Error inesperado: {e}"
        }
