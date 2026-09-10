"""
Interfaz de usuario moderna con CustomTkinter para ZaraWeatherSync.
Incluye:
- Detección automática por IP con opción de fijar ubicación permanente y recomendación.
- Catálogo de 57 ciudades mundiales predefinidas y coordenadas manuales.
- Selector de unidad de temperatura (°C / °F).
- Frecuencia de actualización configurable con validación estricta de límites de Open-Meteo API.
- Adaptabilidad total a pantallas con zoom DPI (125%/150%) y barra fija inferior.
"""

import os
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Optional

import customtkinter as ctk

import webbrowser
from core.version import __version__, GITHUB_REPO_FULL, DONATION_URL
from core.updater import check_for_updates, download_update_file, apply_update_and_restart
from core.config import (
    load_config,
    save_config,
    get_base_directory,
    MIN_UPDATE_INTERVAL_MINUTES,
    MAX_UPDATE_INTERVAL_MINUTES,
)
from core.cities import WORLD_CITIES, get_city_names, get_city_coords
from core.weather_service import fetch_weather, get_ip_location
from core.file_writer import write_zara_clima_file, test_directory_writable
from core.autostart import set_autostart, is_autostart_enabled
from ui.tray import SystemTrayManager


class ZaraWeatherApp(ctk.CTk):
    def __init__(self, start_in_tray: bool = False):
        super().__init__()

        # 1. Configuración de Apariencia de CustomTkinter
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Propiedades de la ventana con soporte responsivo y DPI scaling
        self.title("ZaraWeatherSync - Complemento ZaraRadio")
        self.geometry("560x720")
        self.minsize(480, 560)
        self.resizable(True, True)

        # Cargar configuración persistente
        self.config_data = load_config()

        # Rutas de recursos
        self.base_dir = get_base_directory()
        self.icon_path = self.base_dir / "assets" / "icon.ico"
        if not self.icon_path.exists():
            try:
                from assets.make_icon import create_weather_icon
                create_weather_icon(self.base_dir / "assets")
            except Exception:
                pass

        if self.icon_path.exists():
            try:
                self.iconbitmap(str(self.icon_path))
            except Exception:
                pass

        # Variables de estado meteorológico
        self.current_temp: Optional[int] = None
        self.current_humidity: Optional[int] = None
        self.current_unit: str = self.config_data.get("temperature_unit", "celsius")
        self.last_detected_ip_coords: Optional[tuple] = None
        self.detected_location_name = "Detectando ubicación..."
        self.is_updating = False

        # Evento para control del hilo de actualización en segundo plano
        self.stop_event = threading.Event()
        self.manual_trigger_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

        # Administrador de Bandeja del Sistema
        self.tray_manager = SystemTrayManager(
            icon_path=self.icon_path if self.icon_path.exists() else None,
            on_show=self.restore_from_tray,
            on_refresh=self.trigger_manual_update,
            on_exit=self.quit_completely,
        )

        # Interceptar el evento de cierre de ventana (botón X)
        self.protocol("WM_DELETE_WINDOW", self.on_close_clicked)

        # Construir Interfaz con contenedor desplazable (anti-recorte en zoom 125%/150%)
        self._build_ui()

        # Iniciar Bandeja del Sistema
        self.tray_manager.start()

        # Iniciar hilo de sincronización en segundo plano
        self._start_background_worker()

        # Variables para sistema de auto-actualización
        self.latest_update_info: Optional[dict] = None
        self.is_downloading_update: bool = False

        # Manejo de inicio en bandeja si fue invocado por el Registro
        if start_in_tray:
            self.withdraw()
            self.tray_manager.notify(
                "ZaraWeatherSync Iniciado",
                "El complemento se está ejecutando en segundo plano para ZaraRadio."
            )
        else:
            self.deiconify()

        # Comprobación silenciosa de actualizaciones en segundo plano
        self.after(3500, self._start_background_update_check)

    def _build_ui(self):
        """Construye todos los componentes visuales de la aplicación con diseño adaptable a DPI."""
        self.grid_rowconfigure(0, weight=1)   # Contenedor desplazable
        self.grid_rowconfigure(1, weight=0)   # Barra fija inferior
        self.grid_columnconfigure(0, weight=1)

        # ==============================================================
        # ÁREA DE CONTENIDO DESPLAZABLE
        # ==============================================================
        self.scroll_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=(4, 0))
        self.scroll_frame.grid_columnconfigure(0, weight=1)

        # --------------------------------------------------------------
        # 1. ENCABEZADO
        # --------------------------------------------------------------
        header_frame = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, padx=16, pady=(10, 4), sticky="ew")
        header_frame.grid_columnconfigure(0, weight=1)

        header_top_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        header_top_box.grid(row=0, column=0, sticky="ew")
        header_top_box.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header_top_box,
            text="ZaraWeatherSync 🌦️",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#38bdf8"
        )
        title_label.grid(row=0, column=0, sticky="w")

        version_badge = ctk.CTkLabel(
            header_top_box,
            text=f"v{__version__}",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#0284c7",
            fg_color="#0f172a",
            corner_radius=6,
            padx=8,
            pady=2
        )
        version_badge.grid(row=0, column=1, sticky="e")

        subtitle_label = ctk.CTkLabel(
            header_frame,
            text="Sincronizador meteorológico autónomo para ZaraRadio",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#94a3b8"
        )
        subtitle_label.grid(row=1, column=0, sticky="w")

        # --------------------------------------------------------------
        # BANNER DE ACTUALIZACIÓN (Oculto por defecto, visible si hay nueva versión)
        # --------------------------------------------------------------
        self.update_card = ctk.CTkFrame(self.scroll_frame, corner_radius=14, fg_color="#064e3b", border_width=1, border_color="#10b981")
        self.update_card.grid_columnconfigure(0, weight=1)

        update_top = ctk.CTkFrame(self.update_card, fg_color="transparent")
        update_top.grid(row=0, column=0, padx=12, pady=(10, 2), sticky="ew")
        update_top.grid_columnconfigure(0, weight=1)

        self.update_title_label = ctk.CTkLabel(
            update_top,
            text="🎉 ¡Nueva versión disponible en GitHub!",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#6ee7b7"
        )
        self.update_title_label.grid(row=0, column=0, sticky="w")

        close_update_btn = ctk.CTkButton(
            update_top,
            text="✕",
            width=22,
            height=22,
            command=self._hide_update_banner,
            fg_color="transparent",
            hover_color="#047857",
            font=ctk.CTkFont(size=12, weight="bold")
        )
        close_update_btn.grid(row=0, column=1, sticky="e")

        self.update_notes_label = ctk.CTkLabel(
            self.update_card,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#d1fae5",
            justify="left",
            wraplength=460
        )
        self.update_notes_label.grid(row=1, column=0, padx=12, pady=(0, 4), sticky="w")

        # Barra de progreso durante la descarga
        self.download_progress = ctk.CTkProgressBar(self.update_card, height=8, progress_color="#10b981")
        self.download_progress.set(0)

        self.download_status_label = ctk.CTkLabel(
            self.update_card,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="#a7f3d0"
        )

        self.update_btn_box = ctk.CTkFrame(self.update_card, fg_color="transparent")
        self.update_btn_box.grid(row=4, column=0, padx=12, pady=(4, 10), sticky="ew")
        self.update_btn_box.grid_columnconfigure((0, 1), weight=1)

        self.btn_download_update = ctk.CTkButton(
            self.update_btn_box,
            text="⬇ Descargar e Instalar Ahora",
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669",
            text_color="#064e3b",
            command=self._start_download_update
        )
        self.btn_download_update.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        self.btn_view_release = ctk.CTkButton(
            self.update_btn_box,
            text="🌐 Ver en GitHub",
            height=30,
            font=ctk.CTkFont(size=12),
            fg_color="#047857",
            hover_color="#065f46",
            command=self._open_release_notes
        )
        self.btn_view_release.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        # --------------------------------------------------------------
        # 2. TARJETA PRINCIPAL DE CLIMA (Temperatura, Humedad, Última act.)
        # --------------------------------------------------------------
        weather_card = ctk.CTkFrame(self.scroll_frame, corner_radius=16, fg_color="#1e293b", border_width=1, border_color="#334155")
        weather_card.grid(row=2, column=0, padx=16, pady=8, sticky="ew")
        weather_card.grid_columnconfigure((0, 1), weight=1)

        # Columna 1: Temperatura
        temp_box = ctk.CTkFrame(weather_card, fg_color="transparent")
        temp_box.grid(row=0, column=0, padx=12, pady=(12, 4))

        unit_sym = "°F" if self.current_unit == "fahrenheit" else "°C"
        self.temp_label = ctk.CTkLabel(
            temp_box,
            text=f"--{unit_sym}",
            font=ctk.CTkFont(family="Segoe UI", size=44, weight="bold"),
            text_color="#f8fafc"
        )
        self.temp_label.pack()

        self.temp_title = ctk.CTkLabel(
            temp_box,
            text=f"TEMPERATURA ({unit_sym})",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.temp_title.pack()

        # Columna 2: Humedad
        hum_box = ctk.CTkFrame(weather_card, fg_color="transparent")
        hum_box.grid(row=0, column=1, padx=12, pady=(12, 4))

        self.hum_label = ctk.CTkLabel(
            hum_box,
            text="--%",
            font=ctk.CTkFont(family="Segoe UI", size=44, weight="bold"),
            text_color="#f8fafc"
        )
        self.hum_label.pack()

        hum_title = ctk.CTkLabel(
            hum_box,
            text="HUMEDAD RELATIVA",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#38bdf8"
        )
        hum_title.pack()

        # Fila Inferior de la Tarjeta: Última actualización & Estado
        status_box = ctk.CTkFrame(weather_card, fg_color="#0f172a", corner_radius=10)
        status_box.grid(row=1, column=0, columnspan=2, padx=12, pady=(4, 10), sticky="ew")
        status_box.grid_columnconfigure(0, weight=1)

        self.update_time_label = ctk.CTkLabel(
            status_box,
            text="Última actualización: Esperando sincronización...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#cbd5e1"
        )
        self.update_time_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")

        self.status_badge = ctk.CTkLabel(
            status_box,
            text="Iniciando...",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.status_badge.grid(row=0, column=1, padx=10, pady=5, sticky="e")

        # --------------------------------------------------------------
        # 3. SECCIÓN DE UBICACIÓN (Auto por defecto, Ciudades o Coordenadas)
        # --------------------------------------------------------------
        loc_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=14, fg_color="#1e293b", border_width=1, border_color="#334155")
        loc_frame.grid(row=2, column=0, padx=16, pady=6, sticky="ew")
        loc_frame.grid_columnconfigure(0, weight=1)

        loc_title = ctk.CTkLabel(
            loc_frame,
            text="Selección de Ubicación",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#e2e8f0"
        )
        loc_title.grid(row=0, column=0, padx=14, pady=(10, 4), sticky="w")

        # Selector de 3 Modos: "Automática (IP)", "Ciudad Predefinida", "Coordenadas"
        raw_mode = self.config_data.get("location_mode", "auto")
        if raw_mode == "city":
            initial_mode_text = "Ciudad Predefinida"
        elif raw_mode == "manual":
            initial_mode_text = "Coordenadas"
        else:
            initial_mode_text = "Automática (IP)"

        self.loc_mode_var = ctk.StringVar(value=initial_mode_text)
        self.loc_mode_selector = ctk.CTkSegmentedButton(
            loc_frame,
            values=["Automática (IP)", "Ciudad Predefinida", "Coordenadas"],
            command=self._on_location_mode_changed,
            variable=self.loc_mode_var,
            selected_color="#0284c7",
            selected_hover_color="#0369a1"
        )
        self.loc_mode_selector.grid(row=1, column=0, padx=14, pady=(2, 8), sticky="ew")

        # Contenedor Dinámico para Detalles de Ubicación
        self.loc_details_container = ctk.CTkFrame(loc_frame, fg_color="transparent")
        self.loc_details_container.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")
        self.loc_details_container.grid_columnconfigure(0, weight=1)

        # -- Vista A: Modo Automático con Botón Fijar y Recomendación --
        self.auto_info_box = ctk.CTkFrame(self.loc_details_container, fg_color="#0f172a", corner_radius=10)
        self.auto_info_box.grid_columnconfigure(0, weight=1)

        self.auto_info_label = ctk.CTkLabel(
            self.auto_info_box,
            text="📍 Ubicación Automática activa: detectando por IP pública...",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#38bdf8"
        )
        self.auto_info_label.grid(row=0, column=0, padx=12, pady=(10, 2), sticky="w")

        # Cuadro de aclaración/recomendación
        self.recommendation_box = ctk.CTkFrame(self.auto_info_box, fg_color="#1e293b", corner_radius=8, border_width=1, border_color="#334155")
        self.recommendation_box.grid(row=1, column=0, padx=12, pady=6, sticky="ew")
        self.recommendation_box.grid_columnconfigure(0, weight=1)

        recommendation_text = (
            "💡 Recomendación para Radios:\n"
            "Se recomienda fijar la ubicación con el botón a continuación. Dejar el modo automático "
            "puede provocar que ZaraRadio anuncie el clima de otra localidad si su proveedor de internet (ISP) "
            "o módem 4G asigna dinámicamente una IP de otra provincia o cabecera de red."
        )
        self.rec_label = ctk.CTkLabel(
            self.recommendation_box,
            text=recommendation_text,
            font=ctk.CTkFont(size=11),
            text_color="#cbd5e1",
            justify="left",
            wraplength=460
        )
        self.rec_label.grid(row=0, column=0, padx=10, pady=8, sticky="w")

        # Botón para fijar ubicación permanente
        self.fix_location_btn = ctk.CTkButton(
            self.auto_info_box,
            text="📌 Fijar esta ubicación como fija (Recomendado)",
            height=32,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=self._fix_current_auto_location
        )
        self.fix_location_btn.grid(row=2, column=0, padx=12, pady=(4, 10), sticky="ew")

        # -- Vista B: Menú Desplegable de Ciudades Mundiales --
        self.city_box = ctk.CTkFrame(self.loc_details_container, fg_color="transparent")
        self.city_box.grid_columnconfigure(0, weight=1)

        city_lbl = ctk.CTkLabel(self.city_box, text="Selecciona una ciudad destacada:", font=ctk.CTkFont(size=11), text_color="#94a3b8")
        city_lbl.grid(row=0, column=0, sticky="w", pady=(0, 2))

        self.city_combo = ctk.CTkComboBox(
            self.city_box,
            values=get_city_names(),
            command=self._on_city_selected,
            height=30
        )
        default_city = self.config_data.get("selected_city", "Las Toscas, Santa Fe (Argentina)")
        if default_city in WORLD_CITIES:
            self.city_combo.set(default_city)
        else:
            self.city_combo.set("Las Toscas, Santa Fe (Argentina)")
        self.city_combo.grid(row=1, column=0, sticky="ew")

        self.city_coords_label = ctk.CTkLabel(
            self.city_box,
            text="",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color="#64748b"
        )
        self.city_coords_label.grid(row=2, column=0, sticky="w", pady=(2, 0))

        # -- Vista C: Campos para Coordenadas Manuales --
        self.coords_box = ctk.CTkFrame(self.loc_details_container, fg_color="transparent")
        self.coords_box.grid_columnconfigure((0, 1), weight=1)

        lat_lbl = ctk.CTkLabel(self.coords_box, text="Latitud:", font=ctk.CTkFont(size=11), text_color="#94a3b8")
        lat_lbl.grid(row=0, column=0, sticky="w", padx=2)

        self.lat_entry = ctk.CTkEntry(self.coords_box, height=28, placeholder_text="-28.351")
        self.lat_entry.insert(0, str(self.config_data.get("manual_lat", -28.351)))
        self.lat_entry.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(0, 4))

        lon_lbl = ctk.CTkLabel(self.coords_box, text="Longitud:", font=ctk.CTkFont(size=11), text_color="#94a3b8")
        lon_lbl.grid(row=0, column=1, sticky="w", padx=2)

        self.lon_entry = ctk.CTkEntry(self.coords_box, height=28, placeholder_text="-59.259")
        self.lon_entry.insert(0, str(self.config_data.get("manual_lon", -59.259)))
        self.lon_entry.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(0, 4))

        self.manual_hint = ctk.CTkLabel(
            self.coords_box,
            text="Valores guardados: Las Toscas, Santa Fe (-28.351, -59.259)",
            font=ctk.CTkFont(size=11, slant="italic"),
            text_color="#64748b"
        )
        self.manual_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        # --------------------------------------------------------------
        # 4. CONFIGURACIÓN METEOROLÓGICA Y API (Unidad e Intervalo)
        # --------------------------------------------------------------
        api_cfg_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=14, fg_color="#1e293b", border_width=1, border_color="#334155")
        api_cfg_frame.grid(row=3, column=0, padx=16, pady=6, sticky="ew")
        api_cfg_frame.grid_columnconfigure((0, 1), weight=1)

        api_title = ctk.CTkLabel(
            api_cfg_frame,
            text="Ajustes de Consulta (Open-Meteo API)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#e2e8f0"
        )
        api_title.grid(row=0, column=0, columnspan=2, padx=14, pady=(10, 6), sticky="w")

        # Selector de Unidad: Celsius vs Fahrenheit
        unit_box = ctk.CTkFrame(api_cfg_frame, fg_color="transparent")
        unit_box.grid(row=1, column=0, padx=(14, 6), pady=(0, 10), sticky="ew")
        unit_box.grid_columnconfigure(0, weight=1)

        unit_lbl = ctk.CTkLabel(unit_box, text="Unidad de temperatura:", font=ctk.CTkFont(size=11), text_color="#94a3b8")
        unit_lbl.grid(row=0, column=0, sticky="w", pady=(0, 2))

        init_unit_str = "°F (Fahrenheit)" if self.current_unit == "fahrenheit" else "°C (Celsius)"
        self.unit_var = ctk.StringVar(value=init_unit_str)
        self.unit_selector = ctk.CTkSegmentedButton(
            unit_box,
            values=["°C (Celsius)", "°F (Fahrenheit)"],
            variable=self.unit_var,
            command=self._on_unit_changed,
            selected_color="#0284c7",
            selected_hover_color="#0369a1",
            height=28
        )
        self.unit_selector.grid(row=1, column=0, sticky="ew")

        # Frecuencia de Actualización con Validación de Límites de API
        interval_box = ctk.CTkFrame(api_cfg_frame, fg_color="transparent")
        interval_box.grid(row=1, column=1, padx=(6, 14), pady=(0, 10), sticky="ew")
        interval_box.grid_columnconfigure(0, weight=1)

        interval_lbl = ctk.CTkLabel(
            interval_box,
            text=f"Actualizar cada (mín {MIN_UPDATE_INTERVAL_MINUTES} min):",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        interval_lbl.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))

        self.interval_entry = ctk.CTkEntry(interval_box, height=28, width=70)
        self.interval_entry.insert(0, str(self.config_data.get("update_interval_minutes", 60)))
        self.interval_entry.grid(row=1, column=0, sticky="w")

        apply_interval_btn = ctk.CTkButton(
            interval_box,
            text="Aplicar",
            width=65,
            height=28,
            command=self._apply_interval_change,
            fg_color="#334155",
            hover_color="#475569"
        )
        apply_interval_btn.grid(row=1, column=1, padx=(6, 0), sticky="w")

        # --------------------------------------------------------------
        # 5. SECCIÓN DE RUTA DE SALIDA (ZARARADIO)
        # --------------------------------------------------------------
        path_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=14, fg_color="#1e293b", border_width=1, border_color="#334155")
        path_frame.grid(row=4, column=0, padx=16, pady=6, sticky="ew")
        path_frame.grid_columnconfigure(0, weight=1)

        path_title = ctk.CTkLabel(
            path_frame,
            text="Destino del archivo clima.txt para ZaraRadio",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#e2e8f0"
        )
        path_title.grid(row=0, column=0, padx=14, pady=(10, 4), sticky="w")

        path_select_box = ctk.CTkFrame(path_frame, fg_color="transparent")
        path_select_box.grid(row=1, column=0, padx=14, pady=(0, 6), sticky="ew")
        path_select_box.grid_columnconfigure(0, weight=1)

        self.path_entry = ctk.CTkEntry(path_select_box, height=30)
        self.path_entry.insert(0, self.config_data.get("output_dir", r"C:\ZaraRadio"))
        self.path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        browse_btn = ctk.CTkButton(
            path_select_box,
            text="Examinar...",
            width=95,
            height=30,
            command=self._choose_folder,
            fg_color="#334155",
            hover_color="#475569"
        )
        browse_btn.grid(row=0, column=1)

        # Acciones y estado de acceso de la carpeta
        path_actions_box = ctk.CTkFrame(path_frame, fg_color="transparent")
        path_actions_box.grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")
        path_actions_box.grid_columnconfigure(0, weight=1)

        self.path_status_label = ctk.CTkLabel(
            path_actions_box,
            text="Verificando acceso...",
            font=ctk.CTkFont(size=11),
            text_color="#10b981",
            justify="left",
            wraplength=340
        )
        self.path_status_label.grid(row=0, column=0, sticky="w", pady=(0, 4))

        copy_path_btn = ctk.CTkButton(
            path_actions_box,
            text="📋 Copiar ruta para ZaraRadio",
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._copy_clima_path_to_clipboard
        )
        copy_path_btn.grid(row=0, column=1, sticky="e")

        # --------------------------------------------------------------
        # 6. OPCIONES DE WINDOWS Y BANDEJA
        # --------------------------------------------------------------
        opt_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=14, fg_color="#1e293b", border_width=1, border_color="#334155")
        opt_frame.grid(row=5, column=0, padx=16, pady=6, sticky="ew")
        opt_frame.grid_columnconfigure(0, weight=1)

        self.autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        self.autostart_chk = ctk.CTkCheckBox(
            opt_frame,
            text="Iniciar automáticamente con Windows",
            variable=self.autostart_var,
            command=self._on_autostart_toggle,
            font=ctk.CTkFont(size=12),
            checkbox_width=20,
            checkbox_height=20
        )
        self.autostart_chk.grid(row=0, column=0, padx=14, pady=(8, 4), sticky="w")

        self.minimize_to_tray_var = ctk.BooleanVar(value=self.config_data.get("minimize_to_tray_on_close", True))
        self.minimize_chk = ctk.CTkCheckBox(
            opt_frame,
            text="Minimizar a la bandeja del sistema al cerrar (X)",
            variable=self.minimize_to_tray_var,
            command=self._save_preferences,
            font=ctk.CTkFont(size=12),
            checkbox_width=20,
            checkbox_height=20
        )
        self.minimize_chk.grid(row=1, column=0, padx=14, pady=(4, 10), sticky="w")

        # --------------------------------------------------------------
        # 7. ACERCA DE, ACTUALIZACIONES Y SOPORTE
        # --------------------------------------------------------------
        about_frame = ctk.CTkFrame(self.scroll_frame, corner_radius=14, fg_color="#1e293b", border_width=1, border_color="#334155")
        about_frame.grid(row=6, column=0, padx=16, pady=6, sticky="ew")
        about_frame.grid_columnconfigure((0, 1), weight=1)

        about_title = ctk.CTkLabel(
            about_frame,
            text=f"Acerca de ZaraWeatherSync (v{__version__})",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#e2e8f0"
        )
        about_title.grid(row=0, column=0, columnspan=2, padx=14, pady=(10, 4), sticky="w")

        about_desc = ctk.CTkLabel(
            about_frame,
            text="Sincronizador meteorológico autónomo para ZaraRadio. Código abierto alojado en GitHub.",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8",
            justify="left",
            wraplength=460
        )
        about_desc.grid(row=1, column=0, columnspan=2, padx=14, pady=(0, 8), sticky="w")

        about_btns_box = ctk.CTkFrame(about_frame, fg_color="transparent")
        about_btns_box.grid(row=2, column=0, columnspan=2, padx=14, pady=(0, 10), sticky="ew")
        about_btns_box.grid_columnconfigure((0, 1), weight=1)

        self.btn_check_updates = ctk.CTkButton(
            about_btns_box,
            text="🔍 Buscar Actualizaciones",
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#334155",
            hover_color="#475569",
            command=self._check_updates_manual
        )
        self.btn_check_updates.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        btn_cafecito = ctk.CTkButton(
            about_btns_box,
            text="☕ Donar en Cafecito",
            height=30,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#ea580c",
            hover_color="#c2410c",
            command=self._open_cafecito
        )
        btn_cafecito.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        # ==============================================================
        # BARRA INFERIOR FIJA (Inmune a scroll y zoom DPI)
        # ==============================================================
        footer_bar = ctk.CTkFrame(self, fg_color="#0f172a", corner_radius=0, height=54)
        footer_bar.grid(row=1, column=0, sticky="ew")
        footer_bar.grid_columnconfigure((0, 1), weight=1)

        self.refresh_btn = ctk.CTkButton(
            footer_bar,
            text="🔄 Actualizar Ahora",
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.trigger_manual_update
        )
        self.refresh_btn.grid(row=0, column=0, padx=(16, 6), pady=8, sticky="ew")

        tray_btn = ctk.CTkButton(
            footer_bar,
            text="⬇ Minimizar a Bandeja",
            height=38,
            font=ctk.CTkFont(size=13),
            fg_color="#334155",
            hover_color="#475569",
            command=self.minimize_to_tray
        )
        tray_btn.grid(row=0, column=1, padx=(6, 16), pady=8, sticky="ew")

        # Configurar visibilidad inicial de la sección de ubicación y validar ruta
        self._update_location_ui_view()
        self._validate_current_path()

    def _update_location_ui_view(self):
        """Muestra u oculta los controles específicos según el modo seleccionado."""
        mode_text = self.loc_mode_var.get()

        self.auto_info_box.grid_forget()
        self.city_box.grid_forget()
        self.coords_box.grid_forget()

        if mode_text == "Automática (IP)":
            self.auto_info_box.grid(row=0, column=0, sticky="ew")
            self.config_data["location_mode"] = "auto"
        elif mode_text == "Ciudad Predefinida":
            self.city_box.grid(row=0, column=0, sticky="ew")
            self.config_data["location_mode"] = "city"
            self._update_city_coords_label()
        else:  # Coordenadas
            self.coords_box.grid(row=0, column=0, sticky="ew")
            self.config_data["location_mode"] = "manual"

    def _update_city_coords_label(self):
        """Actualiza el texto descriptivo de las coordenadas de la ciudad elegida."""
        chosen = self.city_combo.get()
        coords = get_city_coords(chosen)
        if coords:
            lat, lon = coords
            self.city_coords_label.configure(text=f"Coordenadas: Lat {lat}, Lon {lon}")

    def _on_location_mode_changed(self, value: str):
        """Manejador al cambiar entre 'Automática', 'Ciudad Predefinida' y 'Coordenadas'."""
        self._update_location_ui_view()
        self._save_preferences()
        self.trigger_manual_update()

    def _fix_current_auto_location(self):
        """
        Transfiere las coordenadas detectadas por IP al modo manual permanente.
        Evita que cambios de IP del ISP alteren la ciudad de la estación de radio.
        """
        if not self.last_detected_ip_coords:
            # Si aún no se completó la primera detección, forzar detección
            success, ip_lat, ip_lon, ip_name = get_ip_location()
            if success:
                self.last_detected_ip_coords = (ip_lat, ip_lon, ip_name)
            else:
                messagebox.showwarning(
                    "Detección en curso",
                    "Aún se está detectando la ubicación por IP pública. Intente nuevamente en unos segundos."
                )
                return

        lat, lon, city_name = self.last_detected_ip_coords

        # 1. Guardar como coordenadas manuales
        self.config_data["manual_lat"] = lat
        self.config_data["manual_lon"] = lon
        self.config_data["manual_city"] = city_name
        self.config_data["location_mode"] = "manual"

        # 2. Actualizar campos de texto de la pestaña Coordenadas
        self.lat_entry.delete(0, "end")
        self.lat_entry.insert(0, str(round(lat, 4)))
        self.lon_entry.delete(0, "end")
        self.lon_entry.insert(0, str(round(lon, 4)))
        self.manual_hint.configure(text=f"Ubicación fija guardada: {city_name} ({round(lat, 4)}, {round(lon, 4)})")

        # 3. Cambiar visualmente al modo "Coordenadas"
        self.loc_mode_var.set("Coordenadas")
        self._update_location_ui_view()

        # 4. Guardar y refrescar
        self._save_preferences()
        self.trigger_manual_update()

        messagebox.showinfo(
            "Ubicación Fijada",
            f"La ubicación se ha establecido como fija exitosamente:\n\n"
            f"📍 {city_name}\n"
            f"Latitud: {lat}\n"
            f"Longitud: {lon}\n\n"
            f"A partir de ahora, la radio mantendrá esta ubicación fija aunque cambie la IP de su proveedor de internet."
        )

    def _on_city_selected(self, city_name: str):
        """Manejador al elegir una ciudad del menú desplegable."""
        self.config_data["selected_city"] = city_name
        self._update_city_coords_label()
        self._save_preferences()
        self.trigger_manual_update()

    def _on_unit_changed(self, value: str):
        """Manejador al cambiar la unidad entre °C y °F."""
        new_unit = "fahrenheit" if "°F" in value else "celsius"
        self.current_unit = new_unit
        self.config_data["temperature_unit"] = new_unit

        sym = "°F" if new_unit == "fahrenheit" else "°C"
        self.temp_title.configure(text=f"TEMPERATURA ({sym})")
        if self.current_temp is not None:
            self.temp_label.configure(text=f"{self.current_temp}{sym}")

        self._save_preferences()
        self.trigger_manual_update()

    def _apply_interval_change(self):
        """
        Valida y aplica la nueva frecuencia de actualización en minutos.
        Aplica las restricciones de la API de Open-Meteo [MIN_UPDATE_INTERVAL_MINUTES - MAX_UPDATE_INTERVAL_MINUTES].
        """
        raw_val = self.interval_entry.get().strip()
        try:
            val = int(raw_val)
        except ValueError:
            messagebox.showerror(
                "Valor Inválido",
                "Por favor ingrese un número entero de minutos para la frecuencia de actualización."
            )
            self.interval_entry.delete(0, "end")
            self.interval_entry.insert(0, str(self.config_data.get("update_interval_minutes", 60)))
            return

        if val < MIN_UPDATE_INTERVAL_MINUTES or val > MAX_UPDATE_INTERVAL_MINUTES:
            err_msg = (
                "⚠️ Restricción de la API de Open-Meteo:\n\n"
                f"Por políticas de uso justo y protección del servicio meteorológico, la frecuencia de actualización "
                f"NO permite valores menores a {MIN_UPDATE_INTERVAL_MINUTES} minutos (para evitar el bloqueo o saturación "
                f"de su dirección IP pública) ni superiores a {MAX_UPDATE_INTERVAL_MINUTES} minutos (24 horas).\n\n"
                f"Por favor introduzca un valor entre {MIN_UPDATE_INTERVAL_MINUTES} y {MAX_UPDATE_INTERVAL_MINUTES} minutos."
            )
            messagebox.showerror("Restricción de API", err_msg)
            self.interval_entry.delete(0, "end")
            self.interval_entry.insert(0, str(self.config_data.get("update_interval_minutes", 60)))
            return

        # Valor válido
        self.config_data["update_interval_minutes"] = val
        self._save_preferences()

        # Despertar el hilo para reprogramar el nuevo intervalo en vivo
        self.manual_trigger_event.set()

        messagebox.showinfo(
            "Frecuencia Actualizada",
            f"Los datos meteorológicos se actualizarán automáticamente cada {val} minutos."
        )

    def _validate_current_path(self):
        """Valida que la carpeta tenga permisos de lectura/escritura y advierte sobre UAC en Archivos de Programa."""
        target = self.path_entry.get().strip() if hasattr(self, "path_entry") else self.config_data.get("output_dir", "")
        writable, msg, is_protected = test_directory_writable(target)
        if not hasattr(self, "path_status_label"):
            return

        if not writable:
            self.path_status_label.configure(text=f"❌ {msg}", text_color="#ef4444")
        elif is_protected:
            self.path_status_label.configure(text=f"⚠️ {msg}", text_color="#f59e0b")
        else:
            self.path_status_label.configure(
                text="✓ Carpeta accesible y con permisos completos para ZaraRadio.",
                text_color="#10b981"
            )

    def _copy_clima_path_to_clipboard(self):
        """Copia la ruta absoluta de clima.txt al portapapeles de Windows para pegarla en ZaraRadio."""
        folder = self.path_entry.get().strip()
        full_path = os.path.normpath(os.path.join(folder, "clima.txt"))
        try:
            self.clipboard_clear()
            self.clipboard_append(full_path)
            messagebox.showinfo(
                "Ruta Copiada para ZaraRadio",
                f"¡Ruta copiada al portapapeles con éxito!\n\n"
                f"📄 {full_path}\n\n"
                f"Cómo configurarlo en ZaraRadio:\n"
                f"1. Abre ZaraRadio y ve al menú 'Herramientas > Opciones > Clima'.\n"
                f"2. En 'Archivo de clima', haz clic derecho y pega (o presiona Ctrl+V).\n"
                f"3. Haz clic en Aceptar."
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo copiar al portapapeles: {e}")

    def _choose_folder(self):
        """Abre diálogo para seleccionar la carpeta de ZaraRadio."""
        current = self.path_entry.get()
        chosen = filedialog.askdirectory(initialdir=current if os.path.exists(current) else None, title="Seleccionar Carpeta de ZaraRadio")
        if chosen:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, os.path.normpath(chosen))
            self.config_data["output_dir"] = os.path.normpath(chosen)
            self._validate_current_path()
            self._save_preferences()
            self.trigger_manual_update()

    def _on_autostart_toggle(self):
        """Activa o desactiva el registro de inicio automático en Windows."""
        enable = self.autostart_var.get()
        success, msg = set_autostart(enable)
        if success:
            self.config_data["autostart"] = enable
            self._save_preferences()
        else:
            messagebox.showwarning("Inicio de Windows", f"No se pudo configurar el inicio automático:\n{msg}")
            self.autostart_var.set(is_autostart_enabled())

    def _save_preferences(self):
        """Persiste las preferencias en config.json."""
        try:
            self.config_data["output_dir"] = self.path_entry.get().strip()
            mode_text = self.loc_mode_var.get()
            if mode_text == "Ciudad Predefinida":
                self.config_data["location_mode"] = "city"
            elif mode_text == "Coordenadas":
                self.config_data["location_mode"] = "manual"
            else:
                self.config_data["location_mode"] = "auto"

            self.config_data["selected_city"] = self.city_combo.get()
            self.config_data["temperature_unit"] = self.current_unit
            self.config_data["minimize_to_tray_on_close"] = self.minimize_to_tray_var.get()
            self.config_data["autostart"] = self.autostart_var.get()

            # Guardar coordenadas manuales si son válidas
            try:
                lat = float(self.lat_entry.get().strip())
                lon = float(self.lon_entry.get().strip())
                self.config_data["manual_lat"] = lat
                self.config_data["manual_lon"] = lon
            except (ValueError, AttributeError):
                pass

            save_config(self.config_data)
        except Exception as e:
            print(f"[ERROR] Error al guardar preferencias: {e}")

    # ==============================================================
    # LÓGICA DE SINCRONIZACIÓN Y CLIMA
    # ==============================================================
    def _start_background_worker(self):
        """Inicia el hilo demonio de actualización periódica."""
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _worker_loop(self):
        """Bucle principal de fondo que ejecuta la consulta cada X minutos."""
        # Ejecución inicial inmediata
        self._perform_update_cycle()

        while not self.stop_event.is_set():
            # Obtener intervalo actualizado dinámicamente
            interval_mins = int(self.config_data.get("update_interval_minutes", 60))
            if interval_mins < MIN_UPDATE_INTERVAL_MINUTES:
                interval_mins = MIN_UPDATE_INTERVAL_MINUTES
            interval_seconds = interval_mins * 60

            triggered = self.manual_trigger_event.wait(timeout=interval_seconds)
            if self.stop_event.is_set():
                break

            if triggered:
                self.manual_trigger_event.clear()

            self._perform_update_cycle()

    def trigger_manual_update(self):
        """Despierta el hilo de trabajo para realizar una actualización inmediata."""
        if not self.is_updating:
            self.manual_trigger_event.set()

    def _perform_update_cycle(self):
        """Ejecuta el ciclo de consulta a Open-Meteo y escritura de clima.txt."""
        self.is_updating = True
        self.after(0, self._set_updating_ui_state, True)

        # 1. Determinar coordenadas según el modo seleccionado
        mode = self.config_data.get("location_mode", "auto")
        lat = self.config_data.get("manual_lat", -28.351)
        lon = self.config_data.get("manual_lon", -59.259)
        location_label = "Ubicación"

        if mode == "auto":
            success_ip, ip_lat, ip_lon, ip_name = get_ip_location()
            if success_ip:
                lat, lon = ip_lat, ip_lon
                location_label = ip_name
                self.detected_location_name = ip_name
                self.last_detected_ip_coords = (ip_lat, ip_lon, ip_name)
            else:
                location_label = "Las Toscas, Santa Fe (Respaldo)"
                self.detected_location_name = "Fallo IP (usando respaldo)"
        elif mode == "city":
            city_name = self.config_data.get("selected_city", "Las Toscas, Santa Fe (Argentina)")
            coords = get_city_coords(city_name)
            if coords:
                lat, lon = coords
                location_label = city_name
            else:
                lat, lon = -28.351, -59.259
                location_label = "Las Toscas, Santa Fe"
        else:  # manual
            try:
                lat = float(self.lat_entry.get().strip())
                lon = float(self.lon_entry.get().strip())
                location_label = f"Lat: {lat}, Lon: {lon}"
            except (ValueError, AttributeError):
                lat = self.config_data.get("manual_lat", -28.351)
                lon = self.config_data.get("manual_lon", -59.259)
                location_label = f"Lat: {lat}, Lon: {lon}"

        # 2. Consultar Open-Meteo con la unidad configurada
        unit = self.config_data.get("temperature_unit", "celsius")
        weather_result = fetch_weather(lat, lon, temperature_unit=unit)

        # 3. Escribir archivo clima.txt si fue exitoso
        out_dir = self.path_entry.get().strip() if hasattr(self, "path_entry") else self.config_data.get("output_dir", "")
        file_success = False
        file_msg = ""

        if weather_result["success"]:
            temp = weather_result["temperature"]
            hum = weather_result["humidity"]
            file_success, file_msg = write_zara_clima_file(out_dir, temp, hum)

        # 4. Actualizar la interfaz en el hilo principal
        self.after(0, self._handle_update_result, weather_result, file_success, file_msg, location_label)

    def _set_updating_ui_state(self, updating: bool):
        """Actualiza el texto y botones durante la consulta."""
        if updating:
            self.refresh_btn.configure(text="⏳ Actualizando...", state="disabled")
            self.status_badge.configure(text="Consultando...", text_color="#38bdf8")
        else:
            self.refresh_btn.configure(text="🔄 Actualizar Ahora", state="normal")

    def _handle_update_result(self, weather_result: dict, file_success: bool, file_msg: str, location_label: str):
        """Procesa y muestra los resultados en pantalla tras la consulta."""
        self.is_updating = False
        self._set_updating_ui_state(False)

        now = datetime.now()
        time_str = now.strftime("%H:%M")

        # Actualizar texto de estado de ubicación automática si aplica
        if self.config_data.get("location_mode") == "auto":
            self.auto_info_label.configure(text=f"📍 Detectada por IP: {self.detected_location_name}")

        sym = "°F" if self.current_unit == "fahrenheit" else "°C"
        if weather_result["success"] and file_success:
            self.current_temp = weather_result["temperature"]
            self.current_humidity = weather_result["humidity"]
            self.temp_label.configure(text=f"{self.current_temp}{sym}")
            self.hum_label.configure(text=f"{self.current_humidity}%")
            self.update_time_label.configure(text=f"Última actualización: {time_str} ({location_label[:26]})")
            self.status_badge.configure(text="✓ Sincronizado", text_color="#10b981")

            # Actualizar tooltip en bandeja del sistema
            if self.tray_manager.icon:
                try:
                    self.tray_manager.icon.title = f"ZaraWeather: {self.current_temp}{sym} | {self.current_humidity}% ({time_str})"
                except Exception:
                    pass
        else:
            err = weather_result.get("error") or file_msg or "Error desconocido"
            self.status_badge.configure(text="⚠️ Error", text_color="#ef4444")
            self.update_time_label.configure(text=f"Fallo a las {time_str}: {err[:32]}...")

    # ==============================================================
    # INTEGRACIÓN CON LA BANDEJA DEL SISTEMA Y VENTANA
    # ==============================================================
    def minimize_to_tray(self):
        """Oculta la ventana en la bandeja del sistema."""
        self.withdraw()
        self.tray_manager.notify(
            "ZaraWeatherSync",
            "La aplicación continúa actualizando clima.txt en segundo plano."
        )

    def restore_from_tray(self):
        """Restaura la ventana en el escritorio desde la bandeja."""
        self.after(0, self._do_restore)

    def _do_restore(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close_clicked(self):
        """Maneja el clic en la X de la ventana."""
        self._save_preferences()
        if self.minimize_to_tray_var.get():
            self.minimize_to_tray()
        else:
            self.quit_completely()

    def quit_completely(self):
        """Cierre definitivo de la aplicación."""
        self._save_preferences()
        self.stop_event.set()
        self.manual_trigger_event.set()
        self.tray_manager.stop()
        self.after(100, self.destroy)

    # ==============================================================
    # SISTEMA DE AUTO-ACTUALIZACIÓN DESDE GITHUB
    # ==============================================================
    def _start_background_update_check(self):
        """Ejecuta una comprobación silenciosa de nuevas versiones en un hilo secundario."""
        threading.Thread(target=self._run_update_check, args=(False,), daemon=True).start()

    def _check_updates_manual(self):
        """Manejador del botón 'Buscar Actualizaciones'."""
        if hasattr(self, "btn_check_updates"):
            self.btn_check_updates.configure(text="⏳ Comprobando...", state="disabled")
        threading.Thread(target=self._run_update_check, args=(True,), daemon=True).start()

    def _run_update_check(self, is_manual: bool):
        """Consulta la API de GitHub Releases y reporta el resultado a la UI."""
        result = check_for_updates()

        if is_manual and hasattr(self, "btn_check_updates"):
            self.after(0, lambda: self.btn_check_updates.configure(text="🔍 Buscar Actualizaciones", state="normal"))

        if result.get("update_available"):
            self.after(0, self._show_update_banner, result)
            if is_manual:
                self.after(0, lambda: messagebox.showinfo(
                    "Actualización Disponible",
                    f"¡Hay una nueva versión disponible en GitHub: {result['latest_version']}!\n\n"
                    f"Puedes hacer clic en 'Descargar e Instalar Ahora' en la parte superior para actualizar automáticamente."
                ))
        else:
            if is_manual:
                err = result.get("error")
                if err:
                    self.after(0, lambda: messagebox.showwarning("Actualizaciones", f"No se pudo consultar GitHub:\n{err}"))
                else:
                    self.after(0, lambda: messagebox.showinfo(
                        "ZaraWeatherSync al Día",
                        f"¡Tienes instalada la versión más reciente (v{__version__})!"
                    ))

    def _show_update_banner(self, update_info: dict):
        """Muestra el banner de actualización en la parte superior."""
        self.latest_update_info = update_info
        ver = update_info.get("latest_version", "Nueva versión")
        notes = update_info.get("release_notes", "").strip()
        if len(notes) > 120:
            notes = notes[:117] + "..."

        self.update_title_label.configure(text=f"🎉 ¡Nueva versión {ver} disponible!")
        self.update_notes_label.configure(text=notes or "Hay una nueva versión disponible en GitHub.")
        self.update_card.grid(row=1, column=0, padx=16, pady=(0, 8), sticky="ew")

    def _hide_update_banner(self):
        """Oculta el banner de actualización."""
        self.update_card.grid_forget()

    def _start_download_update(self):
        """Inicia la descarga de la nueva versión con barra de progreso."""
        if self.is_downloading_update:
            return

        if not self.latest_update_info or not self.latest_update_info.get("download_url"):
            # Si no hay URL directa (ej. release sin asset o dev mode), abrir en navegador
            self._open_release_notes()
            return

        self.is_downloading_update = True
        self.btn_download_update.configure(state="disabled", text="⏳ Descargando...")
        self.download_progress.grid(row=2, column=0, padx=12, pady=(4, 2), sticky="ew")
        self.download_status_label.grid(row=3, column=0, padx=12, pady=(0, 4), sticky="w")
        self.download_status_label.configure(text="Iniciando descarga...")

        download_url = self.latest_update_info["download_url"]
        threading.Thread(target=self._run_download_task, args=(download_url,), daemon=True).start()

    def _run_download_task(self, download_url: str):
        """Descarga el archivo en un hilo secundario y reporta progreso."""
        def on_progress(pct: float, downloaded: int, total: int):
            self.after(0, self._update_download_progress, pct, downloaded, total)

        success, temp_file, err = download_update_file(download_url, progress_callback=on_progress)
        self.after(0, self._on_download_complete, success, temp_file, err)

    def _update_download_progress(self, pct: float, downloaded: int, total: int):
        """Actualiza la barra de progreso y texto en el hilo principal."""
        self.download_progress.set(pct / 100.0)
        mb_down = downloaded / (1024 * 1024)
        mb_tot = total / (1024 * 1024)
        self.download_status_label.configure(
            text=f"Descargando actualización... {pct:.0f}% ({mb_down:.1f} MB / {mb_tot:.1f} MB)"
        )

    def _on_download_complete(self, success: bool, temp_file: Optional[Path], err_msg: str):
        """Manejador al completar o fallar la descarga."""
        self.is_downloading_update = False
        self.btn_download_update.configure(state="normal", text="⬇ Descargar e Instalar Ahora")

        if success and temp_file and temp_file.exists():
            self.download_status_label.configure(text="✓ Descarga completada exitosamente.", text_color="#6ee7b7")

            # Si es binario congelado (.exe), preguntar para reiniciar y reemplazar en caliente
            if getattr(sys, "frozen", False):
                ans = messagebox.askyesno(
                    "Actualización Descargada",
                    f"La nueva versión ({self.latest_update_info.get('latest_version')}) se ha descargado correctamente.\n\n"
                    f"¿Deseas reiniciar la aplicación ahora para completar la actualización?"
                )
                if ans:
                    ok_restart, restart_msg = apply_update_and_restart(temp_file)
                    if ok_restart:
                        self.quit_completely()
                    else:
                        messagebox.showerror("Error al Actualizar", restart_msg)
            else:
                messagebox.showinfo(
                    "Modo Desarrollo",
                    f"El archivo actualizado se guardó en:\n{temp_file}\n\n"
                    f"En modo desarrollo debe compilar o actualizar desde Git."
                )
        else:
            self.download_status_label.configure(text="❌ Falló la descarga.", text_color="#ef4444")
            messagebox.showerror("Error de Descarga", f"No se pudo descargar la actualización:\n{err_msg}")

    def _open_release_notes(self):
        """Abre la página del release en GitHub en el navegador predeterminado."""
        url = (self.latest_update_info or {}).get("html_url") or f"https://github.com/{GITHUB_REPO_FULL}/releases"
        webbrowser.open(url)

    def _open_cafecito(self):
        """Abre el enlace de donaciones de Cafecito."""
        webbrowser.open(DONATION_URL)

