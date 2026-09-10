"""
Interfaz de usuario moderna con CustomTkinter para ZaraWeatherSync.
Diseño compacto de tamaño fijo con navegación por vistas:
- Pantalla Principal de Clima (Monitor en Vivo): Tarjetas legibles de temperatura, humedad, última sincronización y estado.
- Pantalla de Configuración: Ajustes de ubicación, unidades, frecuencia de actualización con validación API,
  carpeta de ZaraRadio, inicio automático y soporte.
- Reintento inteligente de conectividad cada 5 minutos si ocurre un fallo.
"""

import os
import sys
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

        # Ventana compacta de tamaño fijo (no ocupa toda la pantalla)
        self.title("ZaraWeatherSync - Complemento ZaraRadio")
        window_width = 460
        window_height = 570
        self.resizable(False, False)

        # Centrar en pantalla
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        pos_x = max(0, (sw - window_width) // 2)
        pos_y = max(0, (sh - window_height) // 2)
        self.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")

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
        self.last_update_failed = False

        # Evento para control del hilo de sincronización
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

        # Construir Interfaz de Usuario
        self._build_ui()

        # Iniciar Bandeja del Sistema
        self.tray_manager.start()

        # Iniciar hilo de sincronización en segundo plano
        self._start_background_worker()

        # Variables para sistema de auto-actualización
        self.latest_update_info: Optional[dict] = None
        self.is_downloading_update: bool = False

        # Manejo de inicio en bandeja
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

    # ==============================================================
    # CONSTRUCCIÓN DE LA INTERFAZ
    # ==============================================================
    def _build_ui(self):
        """Construye la interfaz compacta con barra de navegación superior y dos pantallas."""
        self.grid_rowconfigure(0, weight=0)  # Barra de navegación fija superior
        self.grid_rowconfigure(1, weight=1)  # Contenedor principal de vistas
        self.grid_columnconfigure(0, weight=1)

        # --------------------------------------------------------------
        # BARRA SUPERIOR PERSISTENTE (Título + Selector de Pestaña)
        # --------------------------------------------------------------
        top_bar = ctk.CTkFrame(self, fg_color="#0f172a", corner_radius=0)
        top_bar.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        top_bar.grid_columnconfigure(0, weight=1)

        header_box = ctk.CTkFrame(top_bar, fg_color="transparent")
        header_box.grid(row=0, column=0, padx=14, pady=(8, 4), sticky="ew")
        header_box.grid_columnconfigure(0, weight=1)

        title_label = ctk.CTkLabel(
            header_box,
            text="ZaraWeatherSync 🌦️",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color="#38bdf8"
        )
        title_label.grid(row=0, column=0, sticky="w")

        version_badge = ctk.CTkLabel(
            header_box,
            text=f"v{__version__}",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color="#38bdf8",
            fg_color="#1e293b",
            corner_radius=6,
            padx=6,
            pady=1
        )
        version_badge.grid(row=0, column=1, sticky="e")

        # Selector de Vista: [ 🌦️ Clima en Vivo ] vs [ ⚙️ Configuración ]
        self.nav_segmented = ctk.CTkSegmentedButton(
            top_bar,
            values=["🌦️ Clima en Vivo", "⚙️ Configuración"],
            command=self._on_nav_tab_changed,
            selected_color="#0284c7",
            selected_hover_color="#0369a1",
            height=30
        )
        self.nav_segmented.set("🌦️ Clima en Vivo")
        self.nav_segmented.grid(row=1, column=0, padx=14, pady=(2, 8), sticky="ew")

        # --------------------------------------------------------------
        # CONTENEDOR PRINCIPAL DE PANTALLAS
        # --------------------------------------------------------------
        self.content_container = ctk.CTkFrame(self, fg_color="transparent")
        self.content_container.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        self.content_container.grid_rowconfigure(0, weight=1)
        self.content_container.grid_columnconfigure(0, weight=1)

        # Construir ambas pantallas
        self._build_monitor_view()
        self._build_config_view()

        # Mostrar por defecto siempre la pantalla de clima
        self._show_view("monitor")

    # ------------------------------------------------------------------
    # PANTALLA 1: MONITOR DE CLIMA EN VIVO
    # ------------------------------------------------------------------
    def _build_monitor_view(self):
        """Pantalla principal de visualización del tiempo y estado para la radio."""
        self.monitor_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self.monitor_frame.grid_columnconfigure(0, weight=1)

        # 1. Banner de Actualización (Oculto hasta que haya versión nueva)
        self.update_card = ctk.CTkFrame(self.monitor_frame, corner_radius=12, fg_color="#064e3b", border_width=1, border_color="#10b981")
        self.update_card.grid_columnconfigure(0, weight=1)

        update_top = ctk.CTkFrame(self.update_card, fg_color="transparent")
        update_top.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="ew")
        update_top.grid_columnconfigure(0, weight=1)

        self.update_title_label = ctk.CTkLabel(
            update_top,
            text="🎉 ¡Nueva versión disponible!",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#6ee7b7"
        )
        self.update_title_label.grid(row=0, column=0, sticky="w")

        close_update_btn = ctk.CTkButton(
            update_top,
            text="✕",
            width=20,
            height=20,
            command=self._hide_update_banner,
            fg_color="transparent",
            hover_color="#047857",
            font=ctk.CTkFont(size=11, weight="bold")
        )
        close_update_btn.grid(row=0, column=1, sticky="e")

        self.update_notes_label = ctk.CTkLabel(
            self.update_card,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="#d1fae5",
            justify="left",
            wraplength=400
        )
        self.update_notes_label.grid(row=1, column=0, padx=10, pady=(0, 4), sticky="w")

        self.download_progress = ctk.CTkProgressBar(self.update_card, height=6, progress_color="#10b981")
        self.download_progress.set(0)

        self.download_status_label = ctk.CTkLabel(
            self.update_card,
            text="",
            font=ctk.CTkFont(size=10),
            text_color="#a7f3d0"
        )

        update_btns = ctk.CTkFrame(self.update_card, fg_color="transparent")
        update_btns.grid(row=4, column=0, padx=10, pady=(2, 8), sticky="ew")
        update_btns.grid_columnconfigure((0, 1), weight=1)

        self.btn_download_update = ctk.CTkButton(
            update_btns,
            text="⬇ Actualizar Ahora",
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#10b981",
            hover_color="#059669",
            text_color="#064e3b",
            command=self._start_download_update
        )
        self.btn_download_update.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.btn_view_release = ctk.CTkButton(
            update_btns,
            text="🌐 Ver en GitHub",
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#047857",
            hover_color="#065f46",
            command=self._open_release_notes
        )
        self.btn_view_release.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        # 2. Tarjeta Métricas Principales (Temperatura y Humedad)
        metrics_card = ctk.CTkFrame(self.monitor_frame, corner_radius=16, fg_color="#1e293b", border_width=1, border_color="#334155")
        metrics_card.grid(row=1, column=0, padx=14, pady=(8, 6), sticky="ew")
        metrics_card.grid_columnconfigure((0, 1), weight=1)

        # Bloque Temperatura
        temp_box = ctk.CTkFrame(metrics_card, fg_color="transparent")
        temp_box.grid(row=0, column=0, padx=10, pady=(14, 10))

        unit_sym = "°F" if self.current_unit == "fahrenheit" else "°C"
        self.temp_label = ctk.CTkLabel(
            temp_box,
            text=f"--{unit_sym}",
            font=ctk.CTkFont(family="Segoe UI", size=48, weight="bold"),
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

        # Bloque Humedad
        hum_box = ctk.CTkFrame(metrics_card, fg_color="transparent")
        hum_box.grid(row=0, column=1, padx=10, pady=(14, 10))

        self.hum_label = ctk.CTkLabel(
            hum_box,
            text="--%",
            font=ctk.CTkFont(family="Segoe UI", size=48, weight="bold"),
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

        # 3. Tarjeta de Ubicación Activa y Destino ZaraRadio
        info_card = ctk.CTkFrame(self.monitor_frame, corner_radius=14, fg_color="#1e293b", border_width=1, border_color="#334155")
        info_card.grid(row=2, column=0, padx=14, pady=6, sticky="ew")
        info_card.grid_columnconfigure(0, weight=1)

        # Ubicación
        loc_row = ctk.CTkFrame(info_card, fg_color="transparent")
        loc_row.grid(row=0, column=0, padx=12, pady=(10, 4), sticky="ew")
        loc_row.grid_columnconfigure(0, weight=1)

        self.location_display_label = ctk.CTkLabel(
            loc_row,
            text="📍 Ubicación: Detectando...",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#e2e8f0"
        )
        self.location_display_label.grid(row=0, column=0, sticky="w")

        # Destino Archivo clima.txt
        dest_row = ctk.CTkFrame(info_card, fg_color="#0f172a", corner_radius=8)
        dest_row.grid(row=1, column=0, padx=12, pady=(4, 10), sticky="ew")
        dest_row.grid_columnconfigure(0, weight=1)

        self.monitor_path_label = ctk.CTkLabel(
            dest_row,
            text=f"📄 {self.config_data.get('output_dir', r'C:\ZaraRadio')}\\clima.txt",
            font=ctk.CTkFont(size=11),
            text_color="#94a3b8"
        )
        self.monitor_path_label.grid(row=0, column=0, padx=8, pady=4, sticky="w")

        btn_copy_quick = ctk.CTkButton(
            dest_row,
            text="📋 Copiar",
            width=65,
            height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._copy_clima_path_to_clipboard
        )
        btn_copy_quick.grid(row=0, column=1, padx=6, pady=4, sticky="e")

        # 4. Estado de Sincronización y Reintentos
        status_box = ctk.CTkFrame(self.monitor_frame, corner_radius=12, fg_color="#0f172a", border_width=1, border_color="#1e293b")
        status_box.grid(row=3, column=0, padx=14, pady=6, sticky="ew")
        status_box.grid_columnconfigure(0, weight=1)

        status_top = ctk.CTkFrame(status_box, fg_color="transparent")
        status_top.grid(row=0, column=0, padx=12, pady=(8, 2), sticky="ew")
        status_top.grid_columnconfigure(0, weight=1)

        self.update_time_label = ctk.CTkLabel(
            status_top,
            text="Última actualización: Esperando sincronización...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#cbd5e1"
        )
        self.update_time_label.grid(row=0, column=0, sticky="w")

        self.status_badge = ctk.CTkLabel(
            status_top,
            text="Iniciando...",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.status_badge.grid(row=0, column=1, sticky="e")

        self.next_update_label = ctk.CTkLabel(
            status_box,
            text="Próxima sincronización automática en espera...",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#64748b"
        )
        self.next_update_label.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="w")

        # 5. Barra Inferior de Acciones
        actions_bar = ctk.CTkFrame(self.monitor_frame, fg_color="transparent")
        actions_bar.grid(row=4, column=0, padx=14, pady=(8, 10), sticky="ew")
        actions_bar.grid_columnconfigure((0, 1), weight=1)

        self.refresh_btn = ctk.CTkButton(
            actions_bar,
            text="🔄 Actualizar Ahora",
            height=38,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.trigger_manual_update
        )
        self.refresh_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        btn_go_config = ctk.CTkButton(
            actions_bar,
            text="⚙️ Ajustes",
            height=38,
            font=ctk.CTkFont(size=13),
            fg_color="#334155",
            hover_color="#475569",
            command=lambda: self._show_view("config")
        )
        btn_go_config.grid(row=0, column=1, padx=(6, 0), sticky="ew")

        btn_tray_compact = ctk.CTkButton(
            self.monitor_frame,
            text="⬇ Minimizar a Bandeja de Windows",
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="transparent",
            hover_color="#1e293b",
            text_color="#94a3b8",
            command=self.minimize_to_tray
        )
        btn_tray_compact.grid(row=5, column=0, padx=14, pady=(0, 8), sticky="ew")

    # ------------------------------------------------------------------
    # PANTALLA 2: CONFIGURACIÓN
    # ------------------------------------------------------------------
    def _build_config_view(self):
        """Pantalla de opciones y configuración con botón visible para volver al clima."""
        self.config_frame = ctk.CTkFrame(self.content_container, fg_color="transparent")
        self.config_frame.grid_rowconfigure(1, weight=1)
        self.config_frame.grid_columnconfigure(0, weight=1)

        # 1. Cabecera con Botón Volver
        config_top = ctk.CTkFrame(self.config_frame, fg_color="#1e293b", corner_radius=10)
        config_top.grid(row=0, column=0, padx=14, pady=(6, 4), sticky="ew")
        config_top.grid_columnconfigure(1, weight=1)

        btn_back_top = ctk.CTkButton(
            config_top,
            text="← Volver al Clima",
            width=130,
            height=30,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=lambda: self._show_view("monitor")
        )
        btn_back_top.grid(row=0, column=0, padx=8, pady=6, sticky="w")

        cfg_heading = ctk.CTkLabel(
            config_top,
            text="Configuración",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#e2e8f0"
        )
        cfg_heading.grid(row=0, column=1, padx=8, pady=6, sticky="e")

        # 2. Área Desplazable de Ajustes
        self.config_scroll = ctk.CTkScrollableFrame(self.config_frame, fg_color="transparent")
        self.config_scroll.grid(row=1, column=0, padx=6, pady=2, sticky="nsew")
        self.config_scroll.grid_columnconfigure(0, weight=1)

        # -- SECCIÓN 1: SELECCIÓN DE UBICACIÓN --
        loc_card = ctk.CTkFrame(self.config_scroll, corner_radius=12, fg_color="#1e293b", border_width=1, border_color="#334155")
        loc_card.grid(row=0, column=0, padx=8, pady=4, sticky="ew")
        loc_card.grid_columnconfigure(0, weight=1)

        loc_title = ctk.CTkLabel(
            loc_card,
            text="1. Ubicación Meteorológica",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38bdf8"
        )
        loc_title.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")

        raw_mode = self.config_data.get("location_mode", "auto")
        if raw_mode == "city":
            init_mode = "Ciudad Predefinida"
        elif raw_mode == "manual":
            init_mode = "Coordenadas"
        else:
            init_mode = "Automática (IP)"

        self.loc_mode_var = ctk.StringVar(value=init_mode)
        self.loc_mode_selector = ctk.CTkSegmentedButton(
            loc_card,
            values=["Automática (IP)", "Ciudad Predefinida", "Coordenadas"],
            command=self._on_location_mode_changed,
            variable=self.loc_mode_var,
            selected_color="#0284c7",
            selected_hover_color="#0369a1",
            height=28
        )
        self.loc_mode_selector.grid(row=1, column=0, padx=12, pady=(2, 6), sticky="ew")

        self.loc_details_container = ctk.CTkFrame(loc_card, fg_color="transparent")
        self.loc_details_container.grid(row=2, column=0, padx=12, pady=(0, 8), sticky="ew")
        self.loc_details_container.grid_columnconfigure(0, weight=1)

        # Vista Auto
        self.auto_info_box = ctk.CTkFrame(self.loc_details_container, fg_color="#0f172a", corner_radius=8)
        self.auto_info_box.grid_columnconfigure(0, weight=1)

        self.auto_info_label = ctk.CTkLabel(
            self.auto_info_box,
            text="📍 Detectando por IP pública...",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.auto_info_label.grid(row=0, column=0, padx=10, pady=(6, 2), sticky="w")

        rec_box = ctk.CTkFrame(self.auto_info_box, fg_color="#1e293b", corner_radius=6)
        rec_box.grid(row=1, column=0, padx=10, pady=4, sticky="ew")
        rec_box.grid_columnconfigure(0, weight=1)

        rec_text = (
            "💡 Recomendación para Radios: Se aconseja fijar la ubicación "
            "para evitar cambios si su proveedor de internet (ISP) asigna IPs de otras ciudades."
        )
        rec_lbl = ctk.CTkLabel(
            rec_box,
            text=rec_text,
            font=ctk.CTkFont(size=10),
            text_color="#cbd5e1",
            justify="left",
            wraplength=370
        )
        rec_lbl.grid(row=0, column=0, padx=8, pady=6, sticky="w")

        self.fix_location_btn = ctk.CTkButton(
            self.auto_info_box,
            text="📌 Fijar esta ubicación como fija (Recomendado)",
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=self._fix_current_auto_location
        )
        self.fix_location_btn.grid(row=2, column=0, padx=10, pady=(2, 8), sticky="ew")

        # Vista Ciudad
        self.city_box = ctk.CTkFrame(self.loc_details_container, fg_color="transparent")
        self.city_box.grid_columnconfigure(0, weight=1)

        self.city_combo = ctk.CTkComboBox(
            self.city_box,
            values=get_city_names(),
            command=self._on_city_selected,
            height=28
        )
        default_city = self.config_data.get("selected_city", "Las Toscas, Santa Fe (Argentina)")
        if default_city in WORLD_CITIES:
            self.city_combo.set(default_city)
        else:
            self.city_combo.set("Las Toscas, Santa Fe (Argentina)")
        self.city_combo.grid(row=0, column=0, sticky="ew")

        self.city_coords_label = ctk.CTkLabel(
            self.city_box,
            text="",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color="#64748b"
        )
        self.city_coords_label.grid(row=1, column=0, sticky="w", pady=(2, 0))

        # Vista Coordenadas
        self.coords_box = ctk.CTkFrame(self.loc_details_container, fg_color="transparent")
        self.coords_box.grid_columnconfigure((0, 1), weight=1)

        lat_lbl = ctk.CTkLabel(self.coords_box, text="Latitud:", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lat_lbl.grid(row=0, column=0, sticky="w")
        self.lat_entry = ctk.CTkEntry(self.coords_box, height=26, placeholder_text="-28.351")
        self.lat_entry.insert(0, str(self.config_data.get("manual_lat", -28.351)))
        self.lat_entry.grid(row=1, column=0, sticky="ew", padx=(0, 4))

        lon_lbl = ctk.CTkLabel(self.coords_box, text="Longitud:", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        lon_lbl.grid(row=0, column=1, sticky="w")
        self.lon_entry = ctk.CTkEntry(self.coords_box, height=26, placeholder_text="-59.259")
        self.lon_entry.insert(0, str(self.config_data.get("manual_lon", -59.259)))
        self.lon_entry.grid(row=1, column=1, sticky="ew", padx=(4, 0))

        self.manual_hint = ctk.CTkLabel(
            self.coords_box,
            text="Valores guardados: Las Toscas (-28.351, -59.259)",
            font=ctk.CTkFont(size=10, slant="italic"),
            text_color="#64748b"
        )
        self.manual_hint.grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        btn_apply_coords = ctk.CTkButton(
            self.coords_box,
            text="Guardar Coordenadas",
            height=26,
            font=ctk.CTkFont(size=11),
            fg_color="#334155",
            hover_color="#475569",
            command=self._apply_manual_coords
        )
        btn_apply_coords.grid(row=3, column=0, columnspan=2, pady=(4, 0), sticky="ew")

        # -- SECCIÓN 2: AJUSTES DE API Y UNIDADES --
        api_card = ctk.CTkFrame(self.config_scroll, corner_radius=12, fg_color="#1e293b", border_width=1, border_color="#334155")
        api_card.grid(row=1, column=0, padx=8, pady=4, sticky="ew")
        api_card.grid_columnconfigure((0, 1), weight=1)

        api_title = ctk.CTkLabel(
            api_card,
            text="2. Parámetros de Consulta (Open-Meteo)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38bdf8"
        )
        api_title.grid(row=0, column=0, columnspan=2, padx=12, pady=(8, 4), sticky="w")

        # Unidad
        unit_box = ctk.CTkFrame(api_card, fg_color="transparent")
        unit_box.grid(row=1, column=0, padx=(12, 4), pady=(0, 8), sticky="ew")
        unit_box.grid_columnconfigure(0, weight=1)

        unit_lbl = ctk.CTkLabel(unit_box, text="Unidad:", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        unit_lbl.grid(row=0, column=0, sticky="w")

        init_unit = "°F (Fahrenheit)" if self.current_unit == "fahrenheit" else "°C (Celsius)"
        self.unit_var = ctk.StringVar(value=init_unit)
        self.unit_selector = ctk.CTkSegmentedButton(
            unit_box,
            values=["°C (Celsius)", "°F (Fahrenheit)"],
            variable=self.unit_var,
            command=self._on_unit_changed,
            selected_color="#0284c7",
            selected_hover_color="#0369a1",
            height=26
        )
        self.unit_selector.grid(row=1, column=0, sticky="ew")

        # Frecuencia
        freq_box = ctk.CTkFrame(api_card, fg_color="transparent")
        freq_box.grid(row=1, column=1, padx=(4, 12), pady=(0, 8), sticky="ew")
        freq_box.grid_columnconfigure(0, weight=1)

        freq_lbl = ctk.CTkLabel(freq_box, text=f"Intervalo (mín {MIN_UPDATE_INTERVAL_MINUTES} min):", font=ctk.CTkFont(size=10), text_color="#94a3b8")
        freq_lbl.grid(row=0, column=0, columnspan=2, sticky="w")

        self.interval_entry = ctk.CTkEntry(freq_box, height=26, width=65)
        self.interval_entry.insert(0, str(self.config_data.get("update_interval_minutes", 60)))
        self.interval_entry.grid(row=1, column=0, sticky="w")

        apply_interval_btn = ctk.CTkButton(
            freq_box,
            text="Aplicar",
            width=55,
            height=26,
            font=ctk.CTkFont(size=11),
            command=self._apply_interval_change,
            fg_color="#334155",
            hover_color="#475569"
        )
        apply_interval_btn.grid(row=1, column=1, padx=(4, 0), sticky="w")

        # -- SECCIÓN 3: DESTINO ZARARADIO --
        path_card = ctk.CTkFrame(self.config_scroll, corner_radius=12, fg_color="#1e293b", border_width=1, border_color="#334155")
        path_card.grid(row=2, column=0, padx=8, pady=4, sticky="ew")
        path_card.grid_columnconfigure(0, weight=1)

        path_title = ctk.CTkLabel(
            path_card,
            text="3. Destino de clima.txt para ZaraRadio",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38bdf8"
        )
        path_title.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")

        path_box = ctk.CTkFrame(path_card, fg_color="transparent")
        path_box.grid(row=1, column=0, padx=12, pady=(0, 4), sticky="ew")
        path_box.grid_columnconfigure(0, weight=1)

        self.path_entry = ctk.CTkEntry(path_box, height=28)
        self.path_entry.insert(0, self.config_data.get("output_dir", r"C:\ZaraRadio"))
        self.path_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        browse_btn = ctk.CTkButton(
            path_box,
            text="Examinar...",
            width=85,
            height=28,
            command=self._choose_folder,
            fg_color="#334155",
            hover_color="#475569"
        )
        browse_btn.grid(row=0, column=1)

        self.path_status_label = ctk.CTkLabel(
            path_card,
            text="Verificando acceso...",
            font=ctk.CTkFont(size=10),
            text_color="#10b981",
            justify="left",
            wraplength=380
        )
        self.path_status_label.grid(row=2, column=0, padx=12, pady=(0, 4), sticky="w")

        btn_copy_path = ctk.CTkButton(
            path_card,
            text="📋 Copiar ruta completa para ZaraRadio",
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._copy_clima_path_to_clipboard
        )
        btn_copy_path.grid(row=3, column=0, padx=12, pady=(2, 8), sticky="ew")

        # -- SECCIÓN 4: OPCIONES DE SISTEMA --
        sys_card = ctk.CTkFrame(self.config_scroll, corner_radius=12, fg_color="#1e293b", border_width=1, border_color="#334155")
        sys_card.grid(row=3, column=0, padx=8, pady=4, sticky="ew")
        sys_card.grid_columnconfigure(0, weight=1)

        sys_title = ctk.CTkLabel(
            sys_card,
            text="4. Opciones de Windows",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38bdf8"
        )
        sys_title.grid(row=0, column=0, padx=12, pady=(8, 4), sticky="w")

        self.autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        self.autostart_chk = ctk.CTkCheckBox(
            sys_card,
            text="Iniciar automáticamente con Windows",
            variable=self.autostart_var,
            command=self._on_autostart_toggle,
            font=ctk.CTkFont(size=11),
            checkbox_width=18,
            checkbox_height=18
        )
        self.autostart_chk.grid(row=1, column=0, padx=12, pady=(2, 4), sticky="w")

        self.minimize_to_tray_var = ctk.BooleanVar(value=self.config_data.get("minimize_to_tray_on_close", True))
        self.minimize_chk = ctk.CTkCheckBox(
            sys_card,
            text="Minimizar a la bandeja del sistema al cerrar (X)",
            variable=self.minimize_to_tray_var,
            command=self._save_preferences,
            font=ctk.CTkFont(size=11),
            checkbox_width=18,
            checkbox_height=18
        )
        self.minimize_chk.grid(row=2, column=0, padx=12, pady=(2, 8), sticky="w")

        # -- SECCIÓN 5: ACTUALIZACIONES Y SOPORTE --
        about_card = ctk.CTkFrame(self.config_scroll, corner_radius=12, fg_color="#1e293b", border_width=1, border_color="#334155")
        about_card.grid(row=4, column=0, padx=8, pady=4, sticky="ew")
        about_card.grid_columnconfigure((0, 1), weight=1)

        about_title = ctk.CTkLabel(
            about_card,
            text=f"5. Acerca de ZaraWeatherSync (v{__version__})",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38bdf8"
        )
        about_title.grid(row=0, column=0, columnspan=2, padx=12, pady=(8, 4), sticky="w")

        self.btn_check_updates = ctk.CTkButton(
            about_card,
            text="🔍 Buscar Actualizaciones",
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#334155",
            hover_color="#475569",
            command=self._check_updates_manual
        )
        self.btn_check_updates.grid(row=1, column=0, padx=(12, 4), pady=(0, 8), sticky="ew")

        btn_cafecito = ctk.CTkButton(
            about_card,
            text="☕ Donar en Cafecito",
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#ea580c",
            hover_color="#c2410c",
            command=self._open_cafecito
        )
        btn_cafecito.grid(row=1, column=1, padx=(4, 12), pady=(0, 8), sticky="ew")

        # 3. Botón Fijo Inferior para Volver al Clima
        btn_back_bottom = ctk.CTkButton(
            self.config_frame,
            text="✓ Guardar y Volver al Monitor de Clima",
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=lambda: self._show_view("monitor")
        )
        btn_back_bottom.grid(row=2, column=0, padx=14, pady=(6, 8), sticky="ew")

        # Inicializar vistas dinámicas de ubicación y ruta
        self._update_location_ui_view()
        self._validate_current_path()

    # ==============================================================
    # NAVEGACIÓN Y CAMBIO DE VISTAS
    # ==============================================================
    def _show_view(self, view_name: str):
        """Muestra u oculta la pantalla activa (monitor o configuración)."""
        if view_name == "config":
            self.monitor_frame.grid_forget()
            self.config_frame.grid(row=0, column=0, sticky="nsew")
            self.nav_segmented.set("⚙️ Configuración")
        else:
            self.config_frame.grid_forget()
            self.monitor_frame.grid(row=0, column=0, sticky="nsew")
            self.nav_segmented.set("🌦️ Clima en Vivo")

    def _on_nav_tab_changed(self, selected_tab: str):
        """Manejador del segmented button de la barra superior."""
        if "Configuración" in selected_tab:
            self._show_view("config")
        else:
            self._show_view("monitor")

    # ==============================================================
    # MANEJADORES DE CONFIGURACIÓN
    # ==============================================================
    def _update_location_ui_view(self):
        """Ajusta los controles visibles según el modo seleccionado."""
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
        """Actualiza el texto con las coordenadas de la ciudad predefinida."""
        chosen = self.city_combo.get()
        coords = get_city_coords(chosen)
        if coords:
            lat, lon = coords
            self.city_coords_label.configure(text=f"Coordenadas: Lat {lat}, Lon {lon}")

    def _on_location_mode_changed(self, value: str):
        """Manejador al alternar entre modo Automático, Ciudad o Coordenadas."""
        self._update_location_ui_view()
        self._save_preferences()
        self.trigger_manual_update()

    def _fix_current_auto_location(self):
        """Fija la ubicación detectada por IP pública como coordenadas permanentes."""
        if not self.last_detected_ip_coords:
            success, ip_lat, ip_lon, ip_name = get_ip_location()
            if success:
                self.last_detected_ip_coords = (ip_lat, ip_lon, ip_name)
            else:
                messagebox.showwarning(
                    "Detección en curso",
                    "Aún se está detectando la ubicación por IP. Intente de nuevo en unos instantes."
                )
                return

        lat, lon, city_name = self.last_detected_ip_coords
        self.config_data["manual_lat"] = lat
        self.config_data["manual_lon"] = lon
        self.config_data["manual_city"] = city_name
        self.config_data["location_mode"] = "manual"

        self.lat_entry.delete(0, "end")
        self.lat_entry.insert(0, str(round(lat, 4)))
        self.lon_entry.delete(0, "end")
        self.lon_entry.insert(0, str(round(lon, 4)))
        self.manual_hint.configure(text=f"Ubicación fija: {city_name} ({round(lat, 4)}, {round(lon, 4)})")

        self.loc_mode_var.set("Coordenadas")
        self._update_location_ui_view()
        self._save_preferences()
        self.trigger_manual_update()

        messagebox.showinfo(
            "Ubicación Fijada con Éxito",
            f"Se fijó permanentemente la ubicación:\n\n"
            f"📍 {city_name}\n"
            f"Latitud: {lat} | Longitud: {lon}\n\n"
            f"ZaraRadio mantendrá esta ubicación fija aunque cambie la IP de su proveedor de internet."
        )

    def _on_city_selected(self, city_name: str):
        """Manejador al seleccionar una ciudad del catálogo."""
        self.config_data["selected_city"] = city_name
        self._update_city_coords_label()
        self._save_preferences()
        self.trigger_manual_update()

    def _apply_manual_coords(self):
        """Valida y guarda las coordenadas manuales ingresadas."""
        try:
            lat = float(self.lat_entry.get().strip())
            lon = float(self.lon_entry.get().strip())
            self.config_data["manual_lat"] = lat
            self.config_data["manual_lon"] = lon
            self.manual_hint.configure(text=f"Valores guardados: Lat {lat}, Lon {lon}")
            self._save_preferences()
            self.trigger_manual_update()
            messagebox.showinfo("Coordenadas Guardadas", f"Nuevas coordenadas aplicadas:\nLatitud: {lat}, Longitud: {lon}")
        except ValueError:
            messagebox.showerror("Error", "Por favor introduzca valores numéricos válidos para latitud y longitud.")

    def _on_unit_changed(self, value: str):
        """Manejador al cambiar entre °C y °F."""
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
        """Valida y aplica la nueva frecuencia de actualización."""
        raw_val = self.interval_entry.get().strip()
        try:
            val = int(raw_val)
        except ValueError:
            messagebox.showerror("Valor Inválido", "Introduzca un número entero de minutos.")
            self.interval_entry.delete(0, "end")
            self.interval_entry.insert(0, str(self.config_data.get("update_interval_minutes", 60)))
            return

        if val < MIN_UPDATE_INTERVAL_MINUTES or val > MAX_UPDATE_INTERVAL_MINUTES:
            err_msg = (
                "⚠️ Restricción de la API de Open-Meteo:\n\n"
                f"Por uso justo del servicio meteorológico gratuito, el intervalo no permite valores menores "
                f"a {MIN_UPDATE_INTERVAL_MINUTES} minutos ni mayores a {MAX_UPDATE_INTERVAL_MINUTES} minutos (24 horas).\n\n"
                f"Introduzca un valor entre {MIN_UPDATE_INTERVAL_MINUTES} y {MAX_UPDATE_INTERVAL_MINUTES}."
            )
            messagebox.showerror("Restricción de API", err_msg)
            self.interval_entry.delete(0, "end")
            self.interval_entry.insert(0, str(self.config_data.get("update_interval_minutes", 60)))
            return

        self.config_data["update_interval_minutes"] = val
        self._save_preferences()
        self.manual_trigger_event.set()
        messagebox.showinfo("Frecuencia Guardada", f"Los datos se actualizarán automáticamente cada {val} minutos.")

    def _validate_current_path(self):
        """Verifica que la carpeta de destino de ZaraRadio sea accesible y con permisos."""
        target = self.path_entry.get().strip() if hasattr(self, "path_entry") else self.config_data.get("output_dir", "")
        writable, msg, is_protected = test_directory_writable(target)

        if hasattr(self, "monitor_path_label"):
            clean_path = os.path.normpath(os.path.join(target, "clima.txt"))
            self.monitor_path_label.configure(text=f"📄 {clean_path}")

        if not hasattr(self, "path_status_label"):
            return

        if not writable:
            self.path_status_label.configure(text=f"❌ {msg}", text_color="#ef4444")
        elif is_protected:
            self.path_status_label.configure(text=f"⚠️ {msg}", text_color="#f59e0b")
        else:
            self.path_status_label.configure(
                text="✓ Carpeta accesible y con permisos de escritura para ZaraRadio.",
                text_color="#10b981"
            )

    def _copy_clima_path_to_clipboard(self):
        """Copia la ruta completa de clima.txt para pegarla directamente en ZaraRadio."""
        folder = self.config_data.get("output_dir", r"C:\ZaraRadio")
        full_path = os.path.normpath(os.path.join(folder, "clima.txt"))
        try:
            self.clipboard_clear()
            self.clipboard_append(full_path)
            messagebox.showinfo(
                "Ruta Copiada",
                f"¡Ruta copiada al portapapeles!\n\n📄 {full_path}\n\n"
                f"Pégala en ZaraRadio en: Herramientas > Opciones > Clima > Archivo de clima."
            )
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo copiar: {e}")

    def _choose_folder(self):
        """Abre diálogo para seleccionar la carpeta de ZaraRadio."""
        current = self.path_entry.get().strip()
        chosen = filedialog.askdirectory(initialdir=current if os.path.exists(current) else None, title="Seleccionar Carpeta de ZaraRadio")
        if chosen:
            clean = os.path.normpath(chosen)
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, clean)
            self.config_data["output_dir"] = clean
            self._validate_current_path()
            self._save_preferences()
            self.trigger_manual_update()

    def _on_autostart_toggle(self):
        """Activa o desactiva el inicio automático con Windows."""
        enable = self.autostart_var.get()
        success, msg = set_autostart(enable)
        if success:
            self.config_data["autostart"] = enable
            self._save_preferences()
        else:
            messagebox.showwarning("Inicio de Windows", f"No se pudo configurar el inicio automático:\n{msg}")
            self.autostart_var.set(is_autostart_enabled())

    def _save_preferences(self):
        """Guarda la configuración en disco."""
        try:
            if hasattr(self, "path_entry"):
                self.config_data["output_dir"] = self.path_entry.get().strip()

            mode_text = self.loc_mode_var.get()
            if mode_text == "Ciudad Predefinida":
                self.config_data["location_mode"] = "city"
            elif mode_text == "Coordenadas":
                self.config_data["location_mode"] = "manual"
            else:
                self.config_data["location_mode"] = "auto"

            if hasattr(self, "city_combo"):
                self.config_data["selected_city"] = self.city_combo.get()
            self.config_data["temperature_unit"] = self.current_unit
            if hasattr(self, "minimize_to_tray_var"):
                self.config_data["minimize_to_tray_on_close"] = self.minimize_to_tray_var.get()
            if hasattr(self, "autostart_var"):
                self.config_data["autostart"] = self.autostart_var.get()

            if hasattr(self, "lat_entry") and hasattr(self, "lon_entry"):
                try:
                    self.config_data["manual_lat"] = float(self.lat_entry.get().strip())
                    self.config_data["manual_lon"] = float(self.lon_entry.get().strip())
                except (ValueError, AttributeError):
                    pass

            save_config(self.config_data)
        except Exception as e:
            print(f"[ERROR] Guardando preferencias: {e}")

    # ==============================================================
    # SINCRONIZACIÓN Y REINTENTO CADA 5 MINUTOS
    # ==============================================================
    def _start_background_worker(self):
        """Inicia el hilo demonio de sincronización en segundo plano."""
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _worker_loop(self):
        """
        Bucle de trabajo con reintento cada 5 minutos ante fallos de conexión.
        Si la última actualización tuvo éxito, espera el intervalo configurado por el usuario.
        """
        # Consulta inicial inmediata
        self._perform_update_cycle()

        while not self.stop_event.is_set():
            if self.last_update_failed:
                # Reintento por fallo de conectividad cada 5 minutos (300 segundos)
                timeout_seconds = 5 * 60
            else:
                interval_mins = int(self.config_data.get("update_interval_minutes", 60))
                if interval_mins < MIN_UPDATE_INTERVAL_MINUTES:
                    interval_mins = MIN_UPDATE_INTERVAL_MINUTES
                timeout_seconds = interval_mins * 60

            # Esperar timeout o interrupción manual
            triggered = self.manual_trigger_event.wait(timeout=timeout_seconds)
            if self.stop_event.is_set():
                break

            if triggered:
                self.manual_trigger_event.clear()

            self._perform_update_cycle()

    def trigger_manual_update(self):
        """Despierta inmediatamente al hilo trabajador para refrescar los datos."""
        if not self.is_updating:
            self.manual_trigger_event.set()

    def _perform_update_cycle(self):
        """Realiza la consulta meteorológica y la escritura en clima.txt."""
        self.is_updating = True
        self.after(0, self._set_updating_ui_state, True)

        # 1. Resolver coordenadas según modo
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
            lat = self.config_data.get("manual_lat", -28.351)
            lon = self.config_data.get("manual_lon", -59.259)
            location_label = f"Coord: {lat}, {lon}"

        # 2. Consultar Open-Meteo
        unit = self.config_data.get("temperature_unit", "celsius")
        weather_result = fetch_weather(lat, lon, temperature_unit=unit)

        # 3. Escribir archivo clima.txt si fue exitoso
        out_dir = self.config_data.get("output_dir", r"C:\ZaraRadio")
        file_success = False
        file_msg = ""

        if weather_result["success"]:
            temp = weather_result["temperature"]
            hum = weather_result["humidity"]
            file_success, file_msg = write_zara_clima_file(out_dir, temp, hum)

        # 4. Actualizar interfaz gráfica
        self.after(0, self._handle_update_result, weather_result, file_success, file_msg, location_label)

    def _set_updating_ui_state(self, updating: bool):
        """Refleja el estado de carga en botones e indicadores."""
        if updating:
            self.refresh_btn.configure(text="⏳ Sincronizando...", state="disabled")
            self.status_badge.configure(text="Consultando...", text_color="#38bdf8")
        else:
            self.refresh_btn.configure(text="🔄 Actualizar Ahora", state="normal")

    def _handle_update_result(self, weather_result: dict, file_success: bool, file_msg: str, location_label: str):
        """Procesa y presenta el resultado del ciclo de actualización."""
        self.is_updating = False
        self._set_updating_ui_state(False)

        now = datetime.now()
        time_str = now.strftime("%H:%M")

        if self.config_data.get("location_mode") == "auto" and hasattr(self, "auto_info_label"):
            self.auto_info_label.configure(text=f"📍 Detectada por IP: {self.detected_location_name}")

        sym = "°F" if self.current_unit == "fahrenheit" else "°C"

        if weather_result["success"] and file_success:
            self.last_update_failed = False
            self.current_temp = weather_result["temperature"]
            self.current_humidity = weather_result["humidity"]

            self.temp_label.configure(text=f"{self.current_temp}{sym}")
            self.hum_label.configure(text=f"{self.current_humidity}%")
            self.update_time_label.configure(text=f"Última actualización: {time_str}")
            self.location_display_label.configure(text=f"📍 {location_label}")
            self.status_badge.configure(text="✓ Sincronizado", text_color="#10b981")

            interval = self.config_data.get("update_interval_minutes", 60)
            self.next_update_label.configure(
                text=f"Próxima sincronización automática en: ~{interval} min",
                text_color="#64748b"
            )

            # Notificar o actualizar tooltip en bandeja
            if self.tray_manager.icon:
                try:
                    self.tray_manager.icon.title = f"ZaraWeather: {self.current_temp}{sym} | {self.current_humidity}% ({time_str})"
                except Exception:
                    pass
        else:
            # Fallo: activar reintento cada 5 minutos
            self.last_update_failed = True
            err = weather_result.get("error") or file_msg or "Error de conexión"
            self.status_badge.configure(text="⚠️ Error de red", text_color="#ef4444")
            self.update_time_label.configure(text=f"Fallo a las {time_str}: {err[:28]}...")
            self.next_update_label.configure(
                text="🔄 Reintentando automáticamente en 5 min por conectividad...",
                text_color="#f59e0b"
            )

    # ==============================================================
    # BANDEJA DEL SISTEMA Y EVENTOS DE VENTANA
    # ==============================================================
    def minimize_to_tray(self):
        """Minimiza la ventana a la bandeja del sistema."""
        self.withdraw()
        self.tray_manager.notify(
            "ZaraWeatherSync",
            "La aplicación continúa sincronizando clima.txt en segundo plano."
        )

    def restore_from_tray(self):
        """Restaura la ventana en el escritorio."""
        self.after(0, self._do_restore)

    def _do_restore(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close_clicked(self):
        """Manejador de la X de cierre."""
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
    # SISTEMA DE ACTUALIZACIÓN EN VIVO (GITHUB)
    # ==============================================================
    def _start_background_update_check(self):
        """Comprueba silenciosamente si hay versiones nuevas."""
        threading.Thread(target=self._run_update_check, args=(False,), daemon=True).start()

    def _check_updates_manual(self):
        """Manejador del botón 'Buscar Actualizaciones'."""
        if hasattr(self, "btn_check_updates"):
            self.btn_check_updates.configure(text="⏳ Comprobando...", state="disabled")
        threading.Thread(target=self._run_update_check, args=(True,), daemon=True).start()

    def _run_update_check(self, is_manual: bool):
        result = check_for_updates()
        if is_manual and hasattr(self, "btn_check_updates"):
            self.after(0, lambda: self.btn_check_updates.configure(text="🔍 Buscar Actualizaciones", state="normal"))

        if result.get("update_available"):
            self.after(0, self._show_update_banner, result)
            if is_manual:
                self.after(0, lambda: messagebox.showinfo(
                    "Actualización Disponible",
                    f"¡Hay una nueva versión disponible: {result['latest_version']}!\n\n"
                    f"Regresa al panel de clima para descargarla con un clic."
                ))
        else:
            if is_manual:
                err = result.get("error")
                if err:
                    self.after(0, lambda: messagebox.showwarning("Actualizaciones", f"No se pudo conectar:\n{err}"))
                else:
                    self.after(0, lambda: messagebox.showinfo(
                        "Al Día",
                        f"¡Tienes instalada la versión más reciente (v{__version__})!"
                    ))

    def _show_update_banner(self, update_info: dict):
        self.latest_update_info = update_info
        ver = update_info.get("latest_version", "Nueva versión")
        notes = update_info.get("release_notes", "").strip()
        if len(notes) > 100:
            notes = notes[:97] + "..."

        self.update_title_label.configure(text=f"🎉 ¡Versión {ver} disponible!")
        self.update_notes_label.configure(text=notes or "Nueva actualización disponible en GitHub.")
        self.update_card.grid(row=0, column=0, padx=14, pady=(6, 4), sticky="ew")

    def _hide_update_banner(self):
        self.update_card.grid_forget()

    def _start_download_update(self):
        if self.is_downloading_update:
            return

        if not self.latest_update_info or not self.latest_update_info.get("download_url"):
            self._open_release_notes()
            return

        self.is_downloading_update = True
        self.btn_download_update.configure(state="disabled", text="⏳ Descargando...")
        self.download_progress.grid(row=2, column=0, padx=10, pady=(2, 2), sticky="ew")
        self.download_status_label.grid(row=3, column=0, padx=10, pady=(0, 2), sticky="w")
        self.download_status_label.configure(text="Iniciando descarga...")

        download_url = self.latest_update_info["download_url"]
        threading.Thread(target=self._run_download_task, args=(download_url,), daemon=True).start()

    def _run_download_task(self, download_url: str):
        def on_progress(pct: float, downloaded: int, total: int):
            self.after(0, self._update_download_progress, pct, downloaded, total)

        success, temp_file, err = download_update_file(download_url, progress_callback=on_progress)
        self.after(0, self._on_download_complete, success, temp_file, err)

    def _update_download_progress(self, pct: float, downloaded: int, total: int):
        self.download_progress.set(pct / 100.0)
        mb_down = downloaded / (1024 * 1024)
        mb_tot = total / (1024 * 1024)
        self.download_status_label.configure(
            text=f"Descargando... {pct:.0f}% ({mb_down:.1f} MB / {mb_tot:.1f} MB)"
        )

    def _on_download_complete(self, success: bool, temp_file: Optional[Path], err_msg: str):
        self.is_downloading_update = False
        self.btn_download_update.configure(state="normal", text="⬇ Actualizar Ahora")

        if success and temp_file and temp_file.exists():
            self.download_status_label.configure(text="✓ Descarga completada.", text_color="#6ee7b7")
            if getattr(sys, "frozen", False):
                ans = messagebox.askyesno(
                    "Actualización Lista",
                    f"La actualización ({self.latest_update_info.get('latest_version')}) está lista.\n\n"
                    f"¿Deseas reiniciar la aplicación ahora para aplicarla?"
                )
                if ans:
                    ok_restart, restart_msg = apply_update_and_restart(temp_file)
                    if ok_restart:
                        self.quit_completely()
                    else:
                        messagebox.showerror("Error", restart_msg)
            else:
                messagebox.showinfo("Modo Desarrollo", f"Archivo descargado en:\n{temp_file}")
        else:
            self.download_status_label.configure(text="❌ Falló la descarga.", text_color="#ef4444")
            messagebox.showerror("Error de Descarga", f"No se pudo descargar:\n{err_msg}")

    def _open_release_notes(self):
        url = (self.latest_update_info or {}).get("html_url") or f"https://github.com/{GITHUB_REPO_FULL}/releases"
        webbrowser.open(url)

    def _open_cafecito(self):
        webbrowser.open(DONATION_URL)
