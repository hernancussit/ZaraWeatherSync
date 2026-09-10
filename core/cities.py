"""
Catálogo de ciudades destacadas de Argentina, Latinoamérica, España y el mundo.
Proporciona coordenadas precalculadas para selección rápida en ZaraWeatherSync.
"""

from typing import Dict, List, Optional, Tuple

# Lista estructurada de ciudades: Nombre display -> (latitud, longitud)
WORLD_CITIES: Dict[str, Tuple[float, float]] = {
    # --- Argentina y Región ---
    "Las Toscas, Santa Fe (Argentina)": (-28.3510, -59.2590),
    "Buenos Aires (Argentina)": (-34.6037, -58.3816),
    "Córdoba (Argentina)": (-31.4201, -64.1888),
    "Rosario, Santa Fe (Argentina)": (-32.9468, -60.6393),
    "Santa Fe Capital (Argentina)": (-31.6333, -60.7000),
    "Mendoza (Argentina)": (-32.8908, -68.8272),
    "San Miguel de Tucumán (Argentina)": (-26.8241, -65.2226),
    "Salta (Argentina)": (-24.7859, -65.4117),
    "Mar del Plata (Argentina)": (-38.0055, -57.5560),
    "Neuquén (Argentina)": (-38.9516, -68.0591),
    "Resistencia, Chaco (Argentina)": (-27.4514, -58.9867),
    "Corrientes (Argentina)": (-27.4692, -58.8306),
    "Posadas, Misiones (Argentina)": (-27.3621, -55.8961),
    "San Juan (Argentina)": (-31.5375, -68.5364),
    "Bahía Blanca (Argentina)": (-38.7183, -62.2663),

    # --- Latinoamérica ---
    "Santiago (Chile)": (-33.4489, -70.6693),
    "Montevideo (Uruguay)": (-34.9011, -56.1645),
    "Asunción (Paraguay)": (-25.2637, -57.5759),
    "Lima (Perú)": (-12.0464, -77.0428),
    "Bogotá (Colombia)": (4.7110, -74.0721),
    "Medellín (Colombia)": (6.2442, -75.5812),
    "Cali (Colombia)": (3.4516, -76.5320),
    "Ciudad de México (México)": (19.4326, -99.1332),
    "Guadalajara (México)": (20.6597, -103.3496),
    "Monterrey (México)": (25.6866, -100.3161),
    "Caracas (Venezuela)": (10.4806, -66.9036),
    "São Paulo (Brasil)": (-23.5505, -46.6333),
    "Río de Janeiro (Brasil)": (-22.9068, -43.1729),
    "Brasilia (Brasil)": (-15.7975, -47.8919),
    "La Paz (Bolivia)": (-16.5000, -68.1500),
    "Santa Cruz de la Sierra (Bolivia)": (-17.7863, -63.1812),
    "Quito (Ecuador)": (-0.1807, -78.4678),
    "Guayaquil (Ecuador)": (-2.1894, -79.8891),
    "San José (Costa Rica)": (9.9281, -84.0907),
    "Ciudad de Panamá (Panamá)": (8.9824, -79.5199),
    "San Salvador (El Salvador)": (13.6929, -89.2182),
    "Ciudad de Guatemala (Guatemala)": (14.6349, -90.5069),

    # --- España ---
    "Madrid (España)": (40.4168, -3.7038),
    "Barcelona (España)": (41.3874, 2.1686),
    "Valencia (España)": (39.4699, -0.3763),
    "Sevilla (España)": (37.3891, -5.9845),
    "Zaragoza (España)": (41.6488, -0.8891),
    "Málaga (España)": (36.7213, -4.4214),
    "Bilbao (España)": (43.2630, -2.9350),

    # --- Estados Unidos y Canadá ---
    "Miami, Florida (EE.UU.)": (25.7617, -80.1918),
    "Nueva York (EE.UU.)": (40.7128, -74.0060),
    "Los Ángeles, California (EE.UU.)": (34.0522, -118.2437),
    "Chicago, Illinois (EE.UU.)": (41.8781, -87.6298),
    "Houston, Texas (EE.UU.)": (29.7604, -95.3698),
    "Toronto (Canadá)": (43.6532, -79.3832),

    # --- Europa y Resto del Mundo ---
    "Londres (Reino Unido)": (51.5074, -0.1278),
    "París (Francia)": (48.8566, 2.3522),
    "Roma (Italia)": (41.9028, 12.4964),
    "Berlín (Alemania)": (52.5200, 13.4050),
    "Lisboa (Portugal)": (38.7223, -9.1393),
    "Tokio (Japón)": (35.6762, 139.6503),
    "Sídney (Australia)": (-33.8688, 151.2093),
}


def get_city_names() -> List[str]:
    """Retorna la lista ordenada de nombres de ciudades disponibles."""
    return list(WORLD_CITIES.keys())


def get_city_coords(city_name: str) -> Optional[Tuple[float, float]]:
    """Retorna las coordenadas (latitud, longitud) de la ciudad especificada."""
    return WORLD_CITIES.get(city_name)
