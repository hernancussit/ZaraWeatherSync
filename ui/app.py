"""
Interfaz de usuario moderna para ZaraWeatherSync.
Diseño idéntico a la captura oficial de pantalla:
- Tarjetas de clima lado a lado (Temperatura y Humedad con sensación térmica, punto de rocío y ubicación).
- Selector de ubicación por pestañas: Automática (IP), Ciudad Predefinida y Coordenadas.
- Configuración de ruta para ZaraRadio (Examinar y Copiar ruta).
- Barra inferior con 3 botones: [Actualizar Ahora] [Configuración] [Minimizar a Bandeja].
- Diálogo flotante modal de Configuración para Unidades, Intervalo (validación 15-1440 min), Autostart, Actualizaciones y Donaciones.
- Ventana compacta y de tamaño fijo (resizable False).
- Reintento automático de conexión cada 5 minutos en caso de fallo de red.
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


def get_weather_icon(weather_code: Optional[int]) -> str:
    """Retorna un emoji representativo del estado del cielo según el código WMO de Open-Meteo."""
    if weather_code is None:
        return "⛅"
    if weather_code == 0:
        return "☀️"
    if weather_code in (1, 2):
        return "🌤️"
    if weather_code == 3:
        return "☁️"
    if weather_code in (45, 48):
        return "🌫️"
    if weather_code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
        return "🌧️"
    if weather_code in (71, 73, 75, 77, 85, 86):
        return "❄️"
    if weather_code in (95, 96, 99):
        return "⛈️"
    return "⛅"


class SettingsDialog(ctk.CTkToplevel):
    """Ventana modal de Ajustes adicionales (Unidades, Intervalo, Windows, Actualizaciones, Donación)."""
    def __init__(self, parent: "ZaraWeatherApp"):
        super().__init__(parent)
        self.parent = parent
        self.title("Ajustes - ZaraWeatherSync")
        w, h = 440, 480
        self.resizable(False, False)

        # Centrar sobre la ventana padre
        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width() - w) // 2
        py = parent.winfo_y() + (parent.winfo_height() - h) // 2
        self.geometry(f"{w}x{h}+{max(0, px)}+{max(0, py)}")

        self.transient(parent)
        self.grab_set()

        self._build_settings_ui()

    def _build_settings_ui(self):
        self.configure(fg_color="#0f172a")

        header = ctk.CTkFrame(self, fg_color="#1e293b", corner_radius=0, height=46)
        header.pack(fill="x", padx=0, pady=(0, 10))

        title = ctk.CTkLabel(
            header,
            text="⚙️ Configuración y Opciones",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#38bdf8"
        )
        title.pack(side="left", padx=14, pady=10)

        # Contenedor con scroll para opciones
        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=14, pady=(0, 10))

        # 1. Unidades de Temperatura
        card_units = ctk.CTkFrame(scroll, fg_color="#1e293b", corner_radius=10)
        card_units.pack(fill="x", pady=5)

        lbl_u = ctk.CTkLabel(card_units, text="Unidad de Temperatura:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#e2e8f0")
        lbl_u.pack(anchor="w", padx=12, pady=(8, 2))

        init_u = "°F (Fahrenheit)" if self.parent.current_unit == "fahrenheit" else "°C (Celsius)"
        self.unit_seg = ctk.CTkSegmentedButton(
            card_units,
            values=["°C (Celsius)", "°F (Fahrenheit)"],
            selected_color="#0284c7",
            selected_hover_color="#0369a1",
            command=self._on_unit_change,
            height=28
        )
        self.unit_seg.set(init_u)
        self.unit_seg.pack(fill="x", padx=12, pady=(2, 10))

        # 2. Frecuencia de Actualización
        card_freq = ctk.CTkFrame(scroll, fg_color="#1e293b", corner_radius=10)
        card_freq.pack(fill="x", pady=5)

        lbl_f = ctk.CTkLabel(
            card_freq,
            text=f"Frecuencia de Actualización (mín {MIN_UPDATE_INTERVAL_MINUTES} min):",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#e2e8f0"
        )
        lbl_f.pack(anchor="w", padx=12, pady=(8, 2))

        freq_row = ctk.CTkFrame(card_freq, fg_color="transparent")
        freq_row.pack(fill="x", padx=12, pady=(2, 10))

        self.entry_freq = ctk.CTkEntry(freq_row, width=80, height=28)
        self.entry_freq.insert(0, str(self.parent.config_data.get("update_interval_minutes", 60)))
        self.entry_freq.pack(side="left", padx=(0, 8))

        btn_apply_f = ctk.CTkButton(
            freq_row,
            text="Aplicar Intervalo",
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self._apply_interval
        )
        btn_apply_f.pack(side="left")

        # 3. Opciones de Windows
        card_win = ctk.CTkFrame(scroll, fg_color="#1e293b", corner_radius=10)
        card_win.pack(fill="x", pady=5)

        lbl_w = ctk.CTkLabel(card_win, text="Opciones de Windows:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#e2e8f0")
        lbl_w.pack(anchor="w", padx=12, pady=(8, 4))

        self.chk_autostart = ctk.CTkCheckBox(
            card_win,
            text="Iniciar automáticamente con Windows",
            variable=self.parent.autostart_var,
            command=self.parent._on_autostart_toggle,
            font=ctk.CTkFont(size=11)
        )
        self.chk_autostart.pack(anchor="w", padx=12, pady=4)

        self.chk_tray = ctk.CTkCheckBox(
            card_win,
            text="Minimizar a la bandeja al cerrar (X)",
            variable=self.parent.minimize_to_tray_var,
            command=self.parent._save_preferences,
            font=ctk.CTkFont(size=11)
        )
        self.chk_tray.pack(anchor="w", padx=12, pady=(4, 10))

        # 4. Actualizaciones y Donación
        card_about = ctk.CTkFrame(scroll, fg_color="#1e293b", corner_radius=10)
        card_about.pack(fill="x", pady=5)

        lbl_ab = ctk.CTkLabel(card_about, text="Soporte y Actualizaciones:", font=ctk.CTkFont(size=12, weight="bold"), text_color="#e2e8f0")
        lbl_ab.pack(anchor="w", padx=12, pady=(8, 4))

        btn_update = ctk.CTkButton(
            card_about,
            text="🔍 Buscar Actualizaciones en GitHub",
            height=28,
            font=ctk.CTkFont(size=11),
            fg_color="#334155",
            hover_color="#475569",
            command=self.parent._check_updates_manual
        )
        btn_update.pack(fill="x", padx=12, pady=4)

        btn_cafe = ctk.CTkButton(
            card_about,
            text="☕ Donar un Cafecito (Apoyar Proyecto)",
            height=28,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#ea580c",
            hover_color="#c2410c",
            command=self.parent._open_cafecito
        )
        btn_cafe.pack(fill="x", padx=12, pady=(4, 10))

        # Botón inferior cerrar
        btn_close = ctk.CTkButton(
            self,
            text="✓ Guardar y Volver",
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.destroy
        )
        btn_close.pack(fill="x", padx=14, pady=(0, 12))

    def _on_unit_change(self, val: str):
        new_u = "fahrenheit" if "°F" in val else "celsius"
        self.parent._change_unit(new_u)

    def _apply_interval(self):
        raw = self.entry_freq.get().strip()
        try:
            val = int(raw)
        except ValueError:
            messagebox.showerror("Error", "Introduzca un número entero de minutos.", parent=self)
            return

        if val < MIN_UPDATE_INTERVAL_MINUTES or val > MAX_UPDATE_INTERVAL_MINUTES:
            messagebox.showerror(
                "Restricción de API",
                f"La API de Open-Meteo no permite valores menores a {MIN_UPDATE_INTERVAL_MINUTES} min "
                f"ni mayores a {MAX_UPDATE_INTERVAL_MINUTES} min para proteger el servicio gratuito.",
                parent=self
            )
            return

        self.parent.config_data["update_interval_minutes"] = val
        self.parent._save_preferences()
        self.parent.manual_trigger_event.set()
        messagebox.showinfo("Intervalo Guardado", f"Actualización automática cada {val} minutos.", parent=self)


class ZaraWeatherApp(ctk.CTk):
    def __init__(self, start_in_tray: bool = False):
        super().__init__()

        # Apariencia CustomTkinter
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Ventana fija y compacta como en el screenshot
        self.title("ZaraWeatherSync")
        window_width = 520
        window_height = 590
        self.resizable(False, False)

        # Centrar en pantalla
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        pos_x = max(0, (sw - window_width) // 2)
        pos_y = max(0, (sh - window_height) // 2)
        self.geometry(f"{window_width}x{window_height}+{pos_x}+{pos_y}")

        # Configuración persistente
        self.config_data = load_config()

        # Iconos
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

        # Variables meteorológicas
        self.current_temp: Optional[int] = None
        self.current_humidity: Optional[int] = None
        self.current_apparent: Optional[int] = None
        self.current_dew_point: Optional[int] = None
        self.current_weather_code: Optional[int] = None
        self.current_unit: str = self.config_data.get("temperature_unit", "celsius")
        self.last_detected_ip_coords: Optional[tuple] = None
        self.detected_location_name = "Detectando..."
        self.active_location_label = "Las Toscas, Santa Fe"
        self.is_updating = False
        self.last_update_failed = False

        # Variables de configuración de Windows
        self.autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        self.minimize_to_tray_var = ctk.BooleanVar(value=self.config_data.get("minimize_to_tray_on_close", True))

        # Eventos para hilo trabajador
        self.stop_event = threading.Event()
        self.manual_trigger_event = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

        # Bandeja del sistema
        self.tray_manager = SystemTrayManager(
            icon_path=self.icon_path if self.icon_path.exists() else None,
            on_show=self.restore_from_tray,
            on_refresh=self.trigger_manual_update,
            on_exit=self.quit_completely,
        )

        self.protocol("WM_DELETE_WINDOW", self.on_close_clicked)

        # Construir Interfaz idéntica al screenshot
        self._build_ui()

        # Iniciar Bandeja
        self.tray_manager.start()

        # Iniciar trabajador de fondo
        self._start_background_worker()

        # Auto-actualizador de GitHub
        self.latest_update_info: Optional[dict] = None
        self.is_downloading_update: bool = False

        if start_in_tray:
            self.withdraw()
            self.tray_manager.notify(
                "ZaraWeatherSync",
                "El complemento se está ejecutando en segundo plano para ZaraRadio."
            )
        else:
            self.deiconify()

        # Comprobación de versiones GitHub
        self.after(3500, self._start_background_update_check)

    # ==============================================================
    # CONSTRUCCIÓN DE LA INTERFAZ (DISEÑO SCREENSHOT)
    # ==============================================================
    def _build_ui(self):
        self.configure(fg_color="#0b111e")

        # --------------------------------------------------------------
        # 1. ENCABEZADO: Título + Subtítulo con Versión
        # --------------------------------------------------------------
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(12, 2))

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(anchor="w")

        title_label = ctk.CTkLabel(
            title_box,
            text="⛅ ZaraWeatherSync",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color="#ffffff"
        )
        title_label.pack(side="left")

        subtitle_label = ctk.CTkLabel(
            header_frame,
            text=f"Sincronizador Meteorológico v{__version__}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#38bdf8"
        )
        subtitle_label.pack(anchor="w", padx=(26, 0))

        # --------------------------------------------------------------
        # 2. LÍNEA DE ESTADO / ÚLTIMA ACTUALIZACIÓN
        # --------------------------------------------------------------
        self.status_line_label = ctk.CTkLabel(
            self,
            text="Última actualización: Esperando sincronización... - Fuente: Open-Meteo",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94a3b8"
        )
        self.status_line_label.pack(anchor="w", padx=16, pady=(2, 6))

        # --------------------------------------------------------------
        # 3. BANNER DE ACTUALIZACIÓN DE GITHUB (Si existe)
        # --------------------------------------------------------------
        self.update_card = ctk.CTkFrame(self, corner_radius=10, fg_color="#064e3b", border_width=1, border_color="#10b981")
        self.update_title_label = ctk.CTkLabel(self.update_card, text="", font=ctk.CTkFont(size=11, weight="bold"), text_color="#6ee7b7")
        self.update_notes_label = ctk.CTkLabel(self.update_card, text="", font=ctk.CTkFont(size=10), text_color="#d1fae5")
        self.download_progress = ctk.CTkProgressBar(self.update_card, height=5, progress_color="#10b981")
        self.download_progress.set(0)
        self.btn_download_update = ctk.CTkButton(
            self.update_card, text="⬇ Actualizar Ahora", height=24, font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#10b981", text_color="#064e3b", hover_color="#059669", command=self._start_download_update
        )

        # --------------------------------------------------------------
        # 4. TARJETAS DE CLIMA: TEMPERATURA Y HUMEDAD LADO A LADO
        # --------------------------------------------------------------
        cards_container = ctk.CTkFrame(self, fg_color="transparent")
        cards_container.pack(fill="x", padx=16, pady=(4, 8))
        cards_container.grid_columnconfigure((0, 1), weight=1, uniform="weather_cards")

        # --- TARJETA 1: TEMPERATURA ---
        self.temp_card = ctk.CTkFrame(cards_container, corner_radius=14, fg_color="#162032", border_width=1, border_color="#24334a")
        self.temp_card.grid(row=0, column=0, padx=(0, 6), sticky="nsew")

        lbl_t_header = ctk.CTkLabel(self.temp_card, text="Temperatura", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color="#38bdf8")
        lbl_t_header.pack(anchor="center", pady=(10, 2))

        temp_mid_box = ctk.CTkFrame(self.temp_card, fg_color="transparent")
        temp_mid_box.pack(anchor="center", pady=2)

        self.temp_icon_label = ctk.CTkLabel(temp_mid_box, text="⛅", font=ctk.CTkFont(size=30))
        self.temp_icon_label.pack(side="left", padx=(0, 6))

        unit_sym = "°F" if self.current_unit == "fahrenheit" else "°C"
        self.temp_value_label = ctk.CTkLabel(
            temp_mid_box,
            text=f"--{unit_sym}",
            font=ctk.CTkFont(family="Segoe UI", size=38, weight="bold"),
            text_color="#ffffff"
        )
        self.temp_value_label.pack(side="left")

        self.feels_like_label = ctk.CTkLabel(
            self.temp_card,
            text=f"Sensación Térmica: --{unit_sym}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94a3b8"
        )
        self.feels_like_label.pack(anchor="center", pady=(2, 2))

        self.temp_loc_label = ctk.CTkLabel(
            self.temp_card,
            text="Las Toscas, Santa Fe",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#cbd5e1"
        )
        self.temp_loc_label.pack(anchor="center", pady=(0, 10))

        # --- TARJETA 2: HUMEDAD RELATIVA ---
        self.hum_card = ctk.CTkFrame(cards_container, corner_radius=14, fg_color="#162032", border_width=1, border_color="#24334a")
        self.hum_card.grid(row=0, column=1, padx=(6, 0), sticky="nsew")

        lbl_h_header = ctk.CTkLabel(self.hum_card, text="Humedad Relativa", font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"), text_color="#38bdf8")
        lbl_h_header.pack(anchor="center", pady=(10, 2))

        hum_mid_box = ctk.CTkFrame(self.hum_card, fg_color="transparent")
        hum_mid_box.pack(anchor="center", pady=2)

        self.hum_icon_label = ctk.CTkLabel(hum_mid_box, text="💧", font=ctk.CTkFont(size=30))
        self.hum_icon_label.pack(side="left", padx=(0, 6))

        self.hum_value_label = ctk.CTkLabel(
            hum_mid_box,
            text="--%",
            font=ctk.CTkFont(family="Segoe UI", size=38, weight="bold"),
            text_color="#ffffff"
        )
        self.hum_value_label.pack(side="left")

        self.dew_point_label = ctk.CTkLabel(
            self.hum_card,
            text=f"Punto de Rocío: --{unit_sym}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#94a3b8"
        )
        self.dew_point_label.pack(anchor="center", pady=(2, 2))

        self.hum_loc_label = ctk.CTkLabel(
            self.hum_card,
            text="Las Toscas, Santa Fe",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#cbd5e1"
        )
        self.hum_loc_label.pack(anchor="center", pady=(0, 10))

        # --------------------------------------------------------------
        # 5. SELECTOR DE UBICACIÓN (PESTAÑAS DEL SCREENSHOT)
        # --------------------------------------------------------------
        loc_container = ctk.CTkFrame(self, fg_color="transparent")
        loc_container.pack(fill="x", padx=16, pady=(4, 6))

        # Pestañas horizontales con iconos idénticas al screenshot
        raw_mode = self.config_data.get("location_mode", "auto")
        if raw_mode == "city":
            init_tab = "📍 Ciudad Predefinida"
        elif raw_mode == "manual":
            init_tab = "🧭 Coordenadas"
        else:
            init_tab = "🌐 Automática (IP)"

        self.loc_tab_var = ctk.StringVar(value=init_tab)
        self.loc_segmented = ctk.CTkSegmentedButton(
            loc_container,
            values=["🌐 Automática (IP)", "📍 Ciudad Predefinida", "🧭 Coordenadas"],
            command=self._on_location_tab_click,
            variable=self.loc_tab_var,
            selected_color="#00a8e8",
            selected_hover_color="#0284c7",
            unselected_color="#162032",
            height=30
        )
        self.loc_segmented.pack(fill="x", pady=(0, 6))

        # Sub-panel dinámico para la pestaña seleccionada
        self.loc_subpanel = ctk.CTkFrame(loc_container, fg_color="#162032", corner_radius=10, border_width=1, border_color="#24334a")
        self.loc_subpanel.pack(fill="x", pady=(0, 4))

        # Sub-vista A: Automática (IP)
        self.box_auto = ctk.CTkFrame(self.loc_subpanel, fg_color="transparent")
        self.lbl_auto_detected = ctk.CTkLabel(
            self.box_auto,
            text="📍 Ubicación Automática: detectando...",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color="#38bdf8"
        )
        self.lbl_auto_detected.pack(anchor="w", padx=10, pady=(6, 2))

        rec_box = ctk.CTkFrame(self.box_auto, fg_color="#0f172a", corner_radius=6)
        rec_box.pack(fill="x", padx=10, pady=2)
        lbl_rec = ctk.CTkLabel(
            rec_box,
            text="💡 Consejo: Se recomienda fijar la ubicación para evitar variaciones por IP dinámica del módem.",
            font=ctk.CTkFont(size=10),
            text_color="#94a3b8",
            wraplength=450,
            justify="left"
        )
        lbl_rec.pack(anchor="w", padx=8, pady=4)

        self.btn_fix_loc = ctk.CTkButton(
            self.box_auto,
            text="📌 Fijar esta ubicación como fija (Recomendado)",
            height=26,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            command=self._fix_auto_location
        )
        self.btn_fix_loc.pack(fill="x", padx=10, pady=(4, 6))

        # Sub-vista B: Ciudad Predefinida
        self.box_city = ctk.CTkFrame(self.loc_subpanel, fg_color="transparent")
        self.city_combo = ctk.CTkComboBox(
            self.box_city,
            values=get_city_names(),
            command=self._on_city_chosen,
            height=28
        )
        def_city = self.config_data.get("selected_city", "Las Toscas, Santa Fe (Argentina)")
        if def_city in WORLD_CITIES:
            self.city_combo.set(def_city)
        else:
            self.city_combo.set("Las Toscas, Santa Fe (Argentina)")
        self.city_combo.pack(fill="x", padx=10, pady=(6, 2))

        self.city_coords_lbl = ctk.CTkLabel(self.box_city, text="", font=ctk.CTkFont(size=10, slant="italic"), text_color="#64748b")
        self.city_coords_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        # Sub-vista C: Coordenadas
        self.box_coords = ctk.CTkFrame(self.loc_subpanel, fg_color="transparent")
        coords_row = ctk.CTkFrame(self.box_coords, fg_color="transparent")
        coords_row.pack(fill="x", padx=10, pady=(6, 2))
        coords_row.grid_columnconfigure((0, 1), weight=1)

        self.entry_lat = ctk.CTkEntry(coords_row, height=26, placeholder_text="Latitud")
        self.entry_lat.insert(0, str(self.config_data.get("manual_lat", -28.351)))
        self.entry_lat.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.entry_lon = ctk.CTkEntry(coords_row, height=26, placeholder_text="Longitud")
        self.entry_lon.insert(0, str(self.config_data.get("manual_lon", -59.259)))
        self.entry_lon.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        btn_save_c = ctk.CTkButton(
            self.box_coords, text="Guardar Coordenadas", height=24, font=ctk.CTkFont(size=10),
            fg_color="#334155", hover_color="#475569", command=self._save_manual_coords
        )
        btn_save_c.pack(fill="x", padx=10, pady=(2, 6))

        # --------------------------------------------------------------
        # 6. CONFIGURACIÓN DE ZARARADIO (IDÉNTICO AL SCREENSHOT)
        # --------------------------------------------------------------
        zara_frame = ctk.CTkFrame(self, fg_color="transparent")
        zara_frame.pack(fill="x", padx=16, pady=(4, 6))

        zara_lbl = ctk.CTkLabel(
            zara_frame,
            text="Configuración de ZaraRadio",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#ffffff"
        )
        zara_lbl.pack(anchor="w", pady=(0, 3))

        zara_row = ctk.CTkFrame(zara_frame, fg_color="transparent")
        zara_row.pack(fill="x")
        zara_row.grid_columnconfigure(0, weight=1)

        self.path_entry = ctk.CTkEntry(
            zara_row,
            height=32,
            fg_color="#162032",
            border_color="#24334a",
            text_color="#ffffff"
        )
        self.path_entry.insert(0, self.config_data.get("output_dir", r"C:\ZaraRadio"))
        self.path_entry.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        btn_browse = ctk.CTkButton(
            zara_row,
            text="Examinar...",
            width=85,
            height=32,
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color="#00a8e8",
            hover_color="#0284c7",
            command=self._choose_folder
        )
        btn_browse.grid(row=0, column=1, padx=(0, 6))

        btn_copy = ctk.CTkButton(
            zara_row,
            text="Copiar ruta para ZaraRadio",
            width=165,
            height=32,
            font=ctk.CTkFont(size=11),
            fg_color="#1e293b",
            hover_color="#334155",
            command=self._copy_clima_path_to_clipboard
        )
        btn_copy.grid(row=0, column=2)

        self.path_status_label = ctk.CTkLabel(
            zara_frame,
            text="Verificando permisos de carpeta...",
            font=ctk.CTkFont(size=10),
            text_color="#10b981"
        )
        self.path_status_label.pack(anchor="w", pady=(2, 0))

        # --------------------------------------------------------------
        # 7. BARRA INFERIOR CON LOS 3 BOTONES DEL SCREENSHOT
        # --------------------------------------------------------------
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=16, pady=(10, 14))
        bottom_bar.grid_columnconfigure((0, 1, 2), weight=1, uniform="bottom_btns")

        # Botón 1: Actualizar Ahora (Cyan)
        self.refresh_btn = ctk.CTkButton(
            bottom_bar,
            text="Actualizar Ahora",
            height=36,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#00c2cb",
            hover_color="#0891b2",
            text_color="#0b111e",
            command=self.trigger_manual_update
        )
        self.refresh_btn.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        # Botón 2: Configuración (Gris/Pizarra)
        btn_settings = ctk.CTkButton(
            bottom_bar,
            text="Configuración",
            height=36,
            font=ctk.CTkFont(size=12),
            fg_color="#2d3748",
            hover_color="#4a5568",
            text_color="#ffffff",
            command=self._open_settings_dialog
        )
        btn_settings.grid(row=0, column=1, padx=5, sticky="ew")

        # Botón 3: Minimizar a Bandeja (Azul)
        btn_tray = ctk.CTkButton(
            bottom_bar,
            text="Minimizar a Bandeja",
            height=36,
            font=ctk.CTkFont(size=12),
            fg_color="#0284c7",
            hover_color="#0369a1",
            text_color="#ffffff",
            command=self.minimize_to_tray
        )
        btn_tray.grid(row=0, column=2, padx=(5, 0), sticky="ew")

        # Configurar vista inicial de pestañas y permisos
        self._update_location_tab_view()
        self._validate_current_path()

    # ==============================================================
    # MANEJO DE PESTAÑAS DE UBICACIÓN
    # ==============================================================
    def _update_location_tab_view(self):
        tab = self.loc_tab_var.get()
        self.box_auto.pack_forget()
        self.box_city.pack_forget()
        self.box_coords.pack_forget()

        if "Automática" in tab:
            self.box_auto.pack(fill="x")
            self.config_data["location_mode"] = "auto"
        elif "Ciudad" in tab:
            self.box_city.pack(fill="x")
            self.config_data["location_mode"] = "city"
            self._update_city_coords_label()
        else:
            self.box_coords.pack(fill="x")
            self.config_data["location_mode"] = "manual"

    def _on_location_tab_click(self, selected_tab: str):
        self._update_location_tab_view()
        self._save_preferences()
        self.trigger_manual_update()

    def _update_city_coords_label(self):
        chosen = self.city_combo.get()
        coords = get_city_coords(chosen)
        if coords:
            lat, lon = coords
            self.city_coords_lbl.configure(text=f"Coordenadas: Lat {lat}, Lon {lon}")

    def _on_city_chosen(self, city_name: str):
        self.config_data["selected_city"] = city_name
        self._update_city_coords_label()
        self._save_preferences()
        self.trigger_manual_update()

    def _fix_auto_location(self):
        if not self.last_detected_ip_coords:
            ok, lat, lon, city = get_ip_location()
            if ok:
                self.last_detected_ip_coords = (lat, lon, city)
            else:
                messagebox.showwarning("Detección", "Aún se está detectando la IP. Espere unos segundos.")
                return

        lat, lon, city = self.last_detected_ip_coords
        self.config_data["manual_lat"] = lat
        self.config_data["manual_lon"] = lon
        self.config_data["manual_city"] = city
        self.config_data["location_mode"] = "manual"

        self.entry_lat.delete(0, "end")
        self.entry_lat.insert(0, str(round(lat, 4)))
        self.entry_lon.delete(0, "end")
        self.entry_lon.insert(0, str(round(lon, 4)))

        self.loc_tab_var.set("🧭 Coordenadas")
        self._update_location_tab_view()
        self._save_preferences()
        self.trigger_manual_update()

        messagebox.showinfo(
            "Ubicación Fijada",
            f"Se ha fijado permanentemente la ubicación de la estación:\n\n"
            f"📍 {city}\nLat: {lat} | Lon: {lon}\n\n"
            f"ZaraRadio mantendrá esta ubicación fija sin verse afectada por cambios de IP de su ISP."
        )

    def _save_manual_coords(self):
        try:
            lat = float(self.entry_lat.get().strip())
            lon = float(self.entry_lon.get().strip())
            self.config_data["manual_lat"] = lat
            self.config_data["manual_lon"] = lon
            self.config_data["location_mode"] = "manual"
            self._save_preferences()
            self.trigger_manual_update()
            messagebox.showinfo("Coordenadas Guardadas", f"Coordenadas aplicadas:\nLat: {lat}, Lon: {lon}")
        except ValueError:
            messagebox.showerror("Error", "Ingrese valores numéricos válidos.")

    # ==============================================================
    # DIÁLOGO DE CONFIGURACIÓN
    # ==============================================================
    def _open_settings_dialog(self):
        SettingsDialog(self)

    def _change_unit(self, new_unit: str):
        self.current_unit = new_unit
        self.config_data["temperature_unit"] = new_unit
        sym = "°F" if new_unit == "fahrenheit" else "°C"
        if self.current_temp is not None:
            self.temp_value_label.configure(text=f"{self.current_temp}{sym}")
        if self.current_apparent is not None:
            self.feels_like_label.configure(text=f"Sensación Térmica: {self.current_apparent}{sym}")
        if self.current_dew_point is not None:
            self.dew_point_label.configure(text=f"Punto de Rocío: {self.current_dew_point}{sym}")
        self._save_preferences()
        self.trigger_manual_update()

    # ==============================================================
    # VERIFICACIÓN DE CARPETA Y ZARARADIO
    # ==============================================================
    def _validate_current_path(self):
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
        folder = self.path_entry.get().strip()
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
        enable = self.autostart_var.get()
        success, msg = set_autostart(enable)
        if success:
            self.config_data["autostart"] = enable
            self._save_preferences()
        else:
            messagebox.showwarning("Inicio de Windows", f"No se pudo configurar:\n{msg}")
            self.autostart_var.set(is_autostart_enabled())

    def _save_preferences(self):
        try:
            if hasattr(self, "path_entry"):
                self.config_data["output_dir"] = self.path_entry.get().strip()

            tab = self.loc_tab_var.get()
            if "Ciudad" in tab:
                self.config_data["location_mode"] = "city"
            elif "Coordenadas" in tab:
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

            if hasattr(self, "entry_lat") and hasattr(self, "entry_lon"):
                try:
                    self.config_data["manual_lat"] = float(self.entry_lat.get().strip())
                    self.config_data["manual_lon"] = float(self.entry_lon.get().strip())
                except (ValueError, AttributeError):
                    pass

            save_config(self.config_data)
        except Exception as e:
            print(f"[ERROR] Guardando preferencias: {e}")

    # ==============================================================
    # HILO DE SINCRONIZACIÓN Y REINTENTO DE 5 MINUTOS
    # ==============================================================
    def _start_background_worker(self):
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _worker_loop(self):
        # Actualización inicial inmediata
        self._perform_update_cycle()

        while not self.stop_event.is_set():
            if self.last_update_failed:
                # Reintento por fallo de red cada 5 minutos (300 segundos)
                timeout_sec = 5 * 60
            else:
                interval_mins = int(self.config_data.get("update_interval_minutes", 60))
                if interval_mins < MIN_UPDATE_INTERVAL_MINUTES:
                    interval_mins = MIN_UPDATE_INTERVAL_MINUTES
                timeout_sec = interval_mins * 60

            triggered = self.manual_trigger_event.wait(timeout=timeout_sec)
            if self.stop_event.is_set():
                break

            if triggered:
                self.manual_trigger_event.clear()

            self._perform_update_cycle()

    def trigger_manual_update(self):
        if not self.is_updating:
            self.manual_trigger_event.set()

    def _perform_update_cycle(self):
        self.is_updating = True
        self.after(0, self._set_updating_ui_state, True)

        mode = self.config_data.get("location_mode", "auto")
        lat = self.config_data.get("manual_lat", -28.351)
        lon = self.config_data.get("manual_lon", -59.259)
        location_name = "Las Toscas, Santa Fe"

        if mode == "auto":
            ok_ip, ip_lat, ip_lon, ip_name = get_ip_location()
            if ok_ip:
                lat, lon = ip_lat, ip_lon
                location_name = ip_name
                self.detected_location_name = ip_name
                self.last_detected_ip_coords = (ip_lat, ip_lon, ip_name)
            else:
                location_name = "Las Toscas, Santa Fe"
        elif mode == "city":
            city_name = self.config_data.get("selected_city", "Las Toscas, Santa Fe (Argentina)")
            coords = get_city_coords(city_name)
            if coords:
                lat, lon = coords
                location_name = city_name.split("(")[0].strip()
            else:
                lat, lon = -28.351, -59.259
                location_name = "Las Toscas, Santa Fe"
        else:
            lat = self.config_data.get("manual_lat", -28.351)
            lon = self.config_data.get("manual_lon", -59.259)
            location_name = f"Lat: {lat}, Lon: {lon}"

        self.active_location_label = location_name

        unit = self.config_data.get("temperature_unit", "celsius")
        weather_result = fetch_weather(lat, lon, temperature_unit=unit)

        out_dir = self.config_data.get("output_dir", r"C:\ZaraRadio")
        file_success = False
        file_msg = ""

        if weather_result["success"]:
            temp = weather_result["temperature"]
            hum = weather_result["humidity"]
            file_success, file_msg = write_zara_clima_file(out_dir, temp, hum)

        self.after(0, self._handle_update_result, weather_result, file_success, file_msg, location_name)

    def _set_updating_ui_state(self, updating: bool):
        if updating:
            self.refresh_btn.configure(text="⏳ Sincronizando...", state="disabled")
            self.status_line_label.configure(
                text="⏳ Sincronizando datos meteorológicos con Open-Meteo...",
                text_color="#38bdf8"
            )
        else:
            self.refresh_btn.configure(text="Actualizar Ahora", state="normal")

    def _handle_update_result(self, weather_result: dict, file_success: bool, file_msg: str, location_name: str):
        self.is_updating = False
        self._set_updating_ui_state(False)

        now = datetime.now()
        time_str = now.strftime("%H:%M:%S (%d/%m/%Y)")
        sym = "°F" if self.current_unit == "fahrenheit" else "°C"

        if "Automática" in self.loc_tab_var.get() and hasattr(self, "lbl_auto_detected"):
            self.lbl_auto_detected.configure(text=f"📍 Detectada por IP: {self.detected_location_name}")

        if weather_result["success"] and file_success:
            self.last_update_failed = False
            self.current_temp = weather_result["temperature"]
            self.current_humidity = weather_result["humidity"]
            self.current_apparent = weather_result.get("apparent_temp")
            self.current_dew_point = weather_result.get("dew_point")
            self.current_weather_code = weather_result.get("weather_code")

            # Actualizar tarjetas principales
            self.temp_icon_label.configure(text=get_weather_icon(self.current_weather_code))
            self.temp_value_label.configure(text=f"{self.current_temp}{sym}")
            if self.current_apparent is not None:
                self.feels_like_label.configure(text=f"Sensación Térmica: {self.current_apparent}{sym}")
            else:
                self.feels_like_label.configure(text=f"Sensación Térmica: {self.current_temp}{sym}")

            self.temp_loc_label.configure(text=location_name[:30])

            self.hum_value_label.configure(text=f"{self.current_humidity}%")
            if self.current_dew_point is not None:
                self.dew_point_label.configure(text=f"Punto de Rocío: {self.current_dew_point}{sym}")
            else:
                self.dew_point_label.configure(text=f"Humedad Relativa: {self.current_humidity}%")

            self.hum_loc_label.configure(text=location_name[:30])

            # Línea de estado
            self.status_line_label.configure(
                text=f"Última actualización: {time_str} - Fuente: Open-Meteo",
                text_color="#94a3b8"
            )

            # Tray tooltip
            if self.tray_manager.icon:
                try:
                    self.tray_manager.icon.title = f"ZaraWeather: {self.current_temp}{sym} | {self.current_humidity}% ({now.strftime('%H:%M')})"
                except Exception:
                    pass
        else:
            # Fallo: Activar reintento cada 5 minutos
            self.last_update_failed = True
            err = weather_result.get("error") or file_msg or "Error de conexión"
            self.status_line_label.configure(
                text=f"⚠️ Error de red ({err[:25]}) - Reintentando automáticamente en 5 min...",
                text_color="#f59e0b"
            )

    # ==============================================================
    # BANDEJA Y EVENTOS
    # ==============================================================
    def minimize_to_tray(self):
        self.withdraw()
        self.tray_manager.notify(
            "ZaraWeatherSync",
            "La aplicación continúa sincronizando clima.txt en segundo plano."
        )

    def restore_from_tray(self):
        self.after(0, self._do_restore)

    def _do_restore(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close_clicked(self):
        self._save_preferences()
        if self.minimize_to_tray_var.get():
            self.minimize_to_tray()
        else:
            self.quit_completely()

    def quit_completely(self):
        self._save_preferences()
        self.stop_event.set()
        self.manual_trigger_event.set()
        self.tray_manager.stop()
        self.after(100, self.destroy)

    # ==============================================================
    # AUTO-ACTUALIZADOR GITHUB
    # ==============================================================
    def _start_background_update_check(self):
        threading.Thread(target=self._run_update_check, args=(False,), daemon=True).start()

    def _check_updates_manual(self):
        threading.Thread(target=self._run_update_check, args=(True,), daemon=True).start()

    def _run_update_check(self, is_manual: bool):
        result = check_for_updates()
        if result.get("update_available"):
            self.after(0, self._show_update_banner, result)
            if is_manual:
                self.after(0, lambda: messagebox.showinfo(
                    "Actualización Disponible",
                    f"¡Hay una nueva versión disponible: {result['latest_version']}!\n\n"
                    f"Se ha activado el banner en la parte superior para descargarla con un clic."
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
        ver = update_info.get("latest_version", "")
        self.update_title_label.configure(text=f"🎉 ¡Versión {ver} disponible en GitHub!")
        self.update_card.pack(fill="x", padx=16, pady=(0, 6), before=self.status_line_label)
        self.update_title_label.pack(side="left", padx=10, pady=4)
        self.btn_download_update.pack(side="right", padx=10, pady=4)

    def _start_download_update(self):
        if self.is_downloading_update:
            return
        if not self.latest_update_info or not self.latest_update_info.get("download_url"):
            self._open_release_notes()
            return

        self.is_downloading_update = True
        self.btn_download_update.configure(state="disabled", text="⏳ Descargando...")
        self.download_progress.pack(fill="x", padx=10, pady=2)
        download_url = self.latest_update_info["download_url"]
        threading.Thread(target=self._run_download_task, args=(download_url,), daemon=True).start()

    def _run_download_task(self, download_url: str):
        def on_progress(pct: float, downloaded: int, total: int):
            self.after(0, lambda: self.download_progress.set(pct / 100.0))

        success, temp_file, err = download_update_file(download_url, progress_callback=on_progress)
        self.after(0, self._on_download_complete, success, temp_file, err)

    def _on_download_complete(self, success: bool, temp_file: Optional[Path], err_msg: str):
        self.is_downloading_update = False
        self.btn_download_update.configure(state="normal", text="⬇ Actualizar Ahora")
        if success and temp_file and temp_file.exists():
            if getattr(sys, "frozen", False):
                ans = messagebox.askyesno(
                    "Actualización Lista",
                    f"La actualización está lista.\n¿Deseas reiniciar la aplicación ahora para aplicarla?"
                )
                if ans:
                    ok_restart, r_msg = apply_update_and_restart(temp_file)
                    if ok_restart:
                        self.quit_completely()
                    else:
                        messagebox.showerror("Error", r_msg)
            else:
                messagebox.showinfo("Modo Desarrollo", f"Descargado en:\n{temp_file}")
        else:
            messagebox.showerror("Error", f"No se pudo descargar:\n{err_msg}")

    def _open_release_notes(self):
        url = (self.latest_update_info or {}).get("html_url") or f"https://github.com/{GITHUB_REPO_FULL}/releases"
        webbrowser.open(url)

    def _open_cafecito(self):
        webbrowser.open(DONATION_URL)
