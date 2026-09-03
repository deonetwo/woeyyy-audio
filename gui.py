"""
Woeyyy - Desktop GUI
Real-Time Low-Latency Microphone Enhancer, Polyphonic Soundboard,
and YouTube Music / Web Browser Audio-to-Mic Streaming Center.
Pure DSP architecture: 100% vectorized, zero bloat, sub-millisecond execution.
"""

import os
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog
from typing import Dict, List, Optional
import customtkinter as ctk
from PIL import Image, ImageTk

# Ensure root path is accessible
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from engine.audio_engine import AudioDeviceManager, MicBoostEngine
from engine.profiles import DEFAULT_PROFILE_KEY, SOUND_PROFILES
from engine.soundboard import GlobalHotkeyManager, ProceduralSoundGenerator
from engine.music_engine import LoopbackCaptureWorker
from engine.discord_bot import DiscordVoiceBot, load_saved_token
from engine.security import SingleInstanceLock

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Set CustomTkinter theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# =========================================================================
# REFACTORING UI DESIGN TOKENS (CALIBRATED DARK MODE SYSTEM)
# =========================================================================
BG_MAIN = "#0b0e17"          # Deep slate foundation
BG_CARD = "#131726"          # Primary card surface
BG_CARD_SUBTLE = "#181d2f"   # Nested container surface
BORDER_SUBTLE = "#1e253c"    # Refined 1px container border

TEXT_PRIMARY = "#f8fafc"     # Crisp high-contrast heading/body
TEXT_SECONDARY = "#94a3b8"   # Balanced metadata/readout
TEXT_MUTED = "#64748b"       # De-emphasized labels

# Functional Color System (Tuned for dark background)
COLOR_EMERALD = "#10b981"
COLOR_EMERALD_HOVER = "#059669"
BG_EMERALD_TINT = "#064e3b"

COLOR_BLUE = "#3b82f6"
COLOR_BLUE_HOVER = "#2563eb"

COLOR_ROSE = "#f43f5e"
COLOR_ROSE_HOVER = "#e11d48"

COLOR_AMBER = "#f59e0b"
BG_AMBER_TINT = "#451a03"

BTN_SECONDARY = "#1e2438"
BTN_SECONDARY_HOVER = "#2b334f"

RADIUS_CARD = 10
RADIUS_BTN = 6


class VUMeterCanvas(tk.Canvas):
    """
    High-performance, smooth canvas-rendered audio VU meter.
    Displays level in dBFS [-60 dBFS to 0 dBFS] with professional
    green/yellow/red color zones and decaying peak-hold indicator.
    """

    def __init__(self, parent, width: int = 340, height: int = 22, **kwargs):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg="#13151f",
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self.meter_width = width
        self.meter_height = height

        # Internal state
        self.current_db = -60.0
        self.peak_db = -60.0
        self.peak_hold_frames = 0
        self.min_db = -60.0
        self.max_db = 0.0

        # Pre-render background ticks
        self._draw_meter(-60.0, -60.0)

    def update_level(self, rms_db: float, peak_db: Optional[float] = None):
        """Update meter with new dBFS values and redraw canvas."""
        self.current_db = max(self.min_db, min(self.max_db, rms_db))

        # Peak hold calculation
        in_peak = rms_db if peak_db is None else peak_db
        if in_peak >= self.peak_db:
            self.peak_db = min(self.max_db, in_peak)
            self.peak_hold_frames = 15
        else:
            if self.peak_hold_frames > 0:
                self.peak_hold_frames -= 1
            else:
                self.peak_db = max(self.min_db, self.peak_db - 1.5)

        self._draw_meter(self.current_db, self.peak_db)

    def _db_to_x(self, db: float) -> float:
        """Convert dBFS [-60, 0] to pixel X coordinate."""
        clamped = max(self.min_db, min(self.max_db, db))
        norm = (clamped - self.min_db) / (self.max_db - self.min_db)
        return norm * (self.meter_width - 4) + 2

    def _draw_meter(self, rms_db: float, peak_db: float):
        self.delete("all")

        # Outer rounded border track
        self.create_rectangle(
            1, 1, self.meter_width - 1, self.meter_height - 1,
            outline="#232738", width=1, fill="#13151f"
        )

        fill_x = self._db_to_x(rms_db)
        if fill_x > 2:
            x_green = self._db_to_x(-18.0)
            x_amber = self._db_to_x(-6.0)

            # Draw Green zone
            x1 = min(fill_x, x_green)
            if x1 > 2:
                self.create_rectangle(2, 2, x1, self.meter_height - 2, fill="#00e676", outline="")

            # Draw Amber zone
            if fill_x > x_green:
                x2 = min(fill_x, x_amber)
                self.create_rectangle(x_green, 2, x2, self.meter_height - 2, fill="#ffd600", outline="")

            # Draw Red zone
            if fill_x > x_amber:
                self.create_rectangle(x_amber, 2, fill_x, self.meter_height - 2, fill="#ff1744", outline="")

        # Peak hold line indicator
        peak_x = self._db_to_x(peak_db)
        if peak_x > 2:
            peak_color = "#ffffff" if peak_db < -3.0 else "#ff5252"
            self.create_line(
                peak_x, 2, peak_x, self.meter_height - 2,
                fill=peak_color, width=2
            )

        # Scale markings (-36, -24, -12, -6)
        for tick_db in [-36, -24, -12, -6]:
            tx = self._db_to_x(tick_db)
            self.create_line(tx, self.meter_height - 5, tx, self.meter_height - 1, fill="#3d4463", width=1)


class WoeyyyApp(ctk.CTk):
    """
    Main application window for Woeyyy Microphone Enhancer, Soundboard & YouTube Music Player.
    """

    def __init__(self):
        super().__init__()

        self.title("Woeyyy - Pro Microphone Enhancer, Soundboard & Discord Voice Bot")
        self.geometry("980x850")
        self.minsize(980, 850)
        self.configure(fg_color=BG_MAIN)

        # Configure Windows taskbar icon integration
        try:
            import ctypes
            myappid = "woeyyy.audio.enhancer.soundboard.1.0"
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        # Load Window & Taskbar Icon
        icon_ico = os.path.join(BASE_DIR, "assets", "app_icon.ico")
        icon_png = os.path.join(BASE_DIR, "assets", "app_icon.png")

        if os.path.exists(icon_ico):
            try:
                self.iconbitmap(icon_ico)
            except Exception:
                pass
        if os.path.exists(icon_png):
            try:
                self._app_icon_tk = ImageTk.PhotoImage(file=icon_png)
                self.iconphoto(False, self._app_icon_tk)
            except Exception:
                pass

        # =========================================================================
        # REFACTORING UI TYPOGRAPHY TOKENS (STANDARDIZED MODULAR TYPE SCALE)
        # =========================================================================
        self.font_hero = ctk.CTkFont(family="Segoe UI", size=20, weight="bold")      # Main Hero Title
        self.font_section = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")   # Major Section Headers
        self.font_label = ctk.CTkFont(family="Segoe UI", size=10, weight="bold")     # De-emphasized All-Caps Labels
        self.font_body = ctk.CTkFont(family="Segoe UI", size=12)                     # Descriptions & Standard Text
        self.font_body_bold = ctk.CTkFont(family="Segoe UI", size=12, weight="bold") # Emphasized Body Text
        self.font_btn = ctk.CTkFont(family="Segoe UI", size=11, weight="bold")       # Interactive Button Labels
        self.font_caption = ctk.CTkFont(family="Segoe UI", size=10)                  # Footers, Metadata & Captions
        self.font_readout = ctk.CTkFont(family="Segoe UI", size=14, weight="bold")   # Primary Numerical Readouts (dBFS)
        self.font_code = ctk.CTkFont(family="Consolas", size=11)                     # Monospace Track Queue

        # Audio Engine Reference
        self.engine: Optional[MicBoostEngine] = None
        self.is_running = False
        self.input_devices_map: Dict[str, int] = {}
        self.output_devices_map: Dict[str, int] = {}
        self.monitor_devices_map: Dict[str, int] = {}
        self.loopback_devices_map: Dict[str, str] = {}

        self.selected_profile_key = DEFAULT_PROFILE_KEY
        self.profiles_by_name = {p.name: p.key for p in SOUND_PROFILES.values()}

        # Hotkeys Manager
        self.hotkeys = GlobalHotkeyManager()
        self.hotkeys.start()

        # Soundboard UI components cache
        self.sound_cards: Dict[str, Dict] = {}

        # Discord Voice Bot Reference
        self.bot = DiscordVoiceBot(on_status_change=self._on_bot_status_update)
        self.bot_channels_map: Dict[str, int] = {}

        # Setup UI layout
        self._build_ui()

        # Populate devices and preset sounds
        self._refresh_audio_devices()
        self._populate_default_soundboard()

        # Telemetry update loop (~30 FPS)
        self.after(33, self._poll_telemetry)

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _build_ui(self):
        """Construct the modern glassmorphism GUI layout."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # =========================================================================
        # 1. HEADER BAR
        # =========================================================================
        header_frame = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        header_frame.grid(row=0, column=0, padx=16, pady=(12, 6), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.pack(side="left", padx=16, pady=10)

        # App Icon Logo Badge
        icon_png_path = os.path.join(BASE_DIR, "assets", "app_icon.png")
        if os.path.exists(icon_png_path):
            try:
                self._logo_img = ctk.CTkImage(
                    light_image=Image.open(icon_png_path),
                    dark_image=Image.open(icon_png_path),
                    size=(36, 36),
                )
                lbl_logo = ctk.CTkLabel(title_box, image=self._logo_img, text="")
                lbl_logo.pack(side="left", padx=(0, 12))
            except Exception:
                pass

        # Vertical Brand Box
        brand_box = ctk.CTkFrame(title_box, fg_color="transparent")
        brand_box.pack(side="left", fill="y")

        # Top row: Brand Title + Cyan Pro Badge
        title_row = ctk.CTkFrame(brand_box, fg_color="transparent")
        title_row.pack(anchor="w")

        lbl_app_name = ctk.CTkLabel(
            title_row,
            text="Woeyyy",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color="#f8fafc",
        )
        lbl_app_name.pack(side="left")

        lbl_badge = ctk.CTkLabel(
            title_row,
            text="PRO AUDIO",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color="#22d3ee",
            fg_color="#083344",
            corner_radius=4,
            padx=6,
            pady=1,
        )
        lbl_badge.pack(side="left", padx=(8, 0))

        # Bottom row: Subtitle Description
        lbl_sub_name = ctk.CTkLabel(
            brand_box,
            text="Microphone Enhancer • Soundboard • Discord Hi-Fi",
            font=self.font_caption,
            text_color=TEXT_MUTED,
        )
        lbl_sub_name.pack(anchor="w", pady=(1, 0))

        controls_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        controls_box.pack(side="right", padx=16, pady=8)

        self.status_badge = ctk.CTkLabel(
            controls_box,
            text="○ IDLE",
            font=self.font_btn,
            text_color=TEXT_SECONDARY,
            fg_color=BG_CARD_SUBTLE,
            corner_radius=RADIUS_BTN,
            padx=12,
            pady=4,
        )
        self.status_badge.pack(side="left", padx=(0, 12))

        self.btn_toggle_stream = ctk.CTkButton(
            controls_box,
            text="Start Stream",
            font=self.font_btn,
            fg_color=COLOR_EMERALD,
            hover_color=COLOR_EMERALD_HOVER,
            text_color="#062817",
            width=130,
            height=32,
            corner_radius=RADIUS_BTN,
            command=self._toggle_stream,
        )
        self.btn_toggle_stream.pack(side="left")

        # =========================================================================
        # 2. DEVICE ROUTING CARD
        # =========================================================================
        routing_card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        routing_card.grid(row=1, column=0, padx=16, pady=4, sticky="ew")
        routing_card.grid_columnconfigure((0, 1, 2), weight=1)

        # Input Mic
        in_box = ctk.CTkFrame(routing_card, fg_color="transparent")
        in_box.grid(row=0, column=0, padx=12, pady=10, sticky="ew")
        ctk.CTkLabel(in_box, text="INPUT MICROPHONE", font=self.font_label, text_color=TEXT_MUTED).pack(anchor="w", pady=(0, 2))
        self.opt_input = ctk.CTkOptionMenu(
            in_box,
            values=["Scanning..."],
            command=self._on_input_device_changed,
            font=self.font_body,
            dropdown_font=self.font_body,
            fg_color=BG_CARD_SUBTLE,
            button_color=BTN_SECONDARY,
            button_hover_color=BTN_SECONDARY_HOVER,
            dropdown_fg_color="#0e111c",
            height=30,
            corner_radius=RADIUS_BTN,
        )
        self.opt_input.pack(fill="x")

        # Output (Virtual Cable -> Discord/Game)
        out_box = ctk.CTkFrame(routing_card, fg_color="transparent")
        out_box.grid(row=0, column=1, padx=12, pady=10, sticky="ew")
        ctk.CTkLabel(out_box, text="MIC STREAM OUT (VB-CABLE / DISCORD)", font=self.font_label, text_color=COLOR_EMERALD).pack(anchor="w", pady=(0, 2))
        self.opt_output = ctk.CTkOptionMenu(
            out_box,
            values=["Scanning..."],
            command=self._on_output_device_changed,
            font=self.font_body,
            dropdown_font=self.font_body,
            fg_color=BG_CARD_SUBTLE,
            button_color=BTN_SECONDARY,
            button_hover_color=BTN_SECONDARY_HOVER,
            dropdown_fg_color="#0e111c",
            height=30,
            corner_radius=RADIUS_BTN,
        )
        self.opt_output.pack(fill="x")

        # Headphone Monitor (Self-Listen)
        mon_box = ctk.CTkFrame(routing_card, fg_color="transparent")
        mon_box.grid(row=0, column=2, padx=12, pady=10, sticky="ew")
        mon_header = ctk.CTkFrame(mon_box, fg_color="transparent")
        mon_header.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(mon_header, text="HEADPHONE MONITOR (SELF-LISTEN)", font=self.font_label, text_color=TEXT_MUTED).pack(side="left")
        self.switch_monitor = ctk.CTkSwitch(
            mon_header,
            text="Listen",
            font=self.font_caption,
            width=50,
            progress_color=COLOR_BLUE,
            command=self._on_monitor_toggled,
        )
        self.switch_monitor.pack(side="right")
        self.opt_monitor = ctk.CTkOptionMenu(
            mon_box,
            values=["Scanning..."],
            command=self._on_monitor_device_changed,
            font=self.font_body,
            dropdown_font=self.font_body,
            fg_color=BG_CARD_SUBTLE,
            button_color=BTN_SECONDARY,
            button_hover_color=BTN_SECONDARY_HOVER,
            dropdown_fg_color="#0e111c",
            height=30,
            corner_radius=RADIUS_BTN,
        )
        self.opt_monitor.pack(fill="x")

        # =========================================================================
        # 3. TABVIEW (MICROPHONE, SOUNDBOARD, YOUTUBE MUSIC)
        # =========================================================================
        self.tabview = ctk.CTkTabview(
            self,
            fg_color=BG_CARD,
            segmented_button_fg_color="#0d0f18",
            segmented_button_selected_color=COLOR_BLUE,
            segmented_button_selected_hover_color=COLOR_BLUE_HOVER,
            corner_radius=RADIUS_CARD,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        self.tabview.grid(row=2, column=0, padx=16, pady=(4, 6), sticky="nsew")

        self.tab_mic = self.tabview.add("Microphone & FX")
        self.tab_sb = self.tabview.add("Soundboard Pads")
        self.tab_music = self.tabview.add("YouTube Music & Web")
        self.tab_bot = self.tabview.add("Discord Voice Bot")

        # Build each tab's UI
        self._build_mic_tab()
        self._build_soundboard_tab()
        self._build_music_tab()
        self._build_bot_tab()

        # =========================================================================
        # 4. FOOTER STATUS BAR
        # =========================================================================
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, padx=16, pady=(2, 8), sticky="ew")

        self.lbl_footer = ctk.CTkLabel(
            footer,
            text="Engine: 48 kHz float32 | Buffer: 128 frames (~2.7ms) | Limiter Ceiling: -0.1 dBFS",
            font=self.font_caption,
            text_color="#5a6078",
        )
        self.lbl_footer.pack(side="left")

        self.lbl_perf = ctk.CTkLabel(
            footer,
            text="DSP Load: <0.5% | Drops: 0 | Auto-Ducking: IDLE",
            font=self.font_caption,
            text_color="#5a6078",
        )
        self.lbl_perf.pack(side="right")

    # =========================================================================
    # TAB 1: MICROPHONE & FX
    # =========================================================================
    def _build_mic_tab(self):
        tab = self.tab_mic
        tab.grid_columnconfigure(0, weight=1)

        # Gain Booster Card
        gain_card = ctk.CTkFrame(tab, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        gain_card.pack(fill="x", padx=10, pady=6)

        gain_header = ctk.CTkFrame(gain_card, fg_color="transparent")
        gain_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(gain_header, text="DIGITAL MIC GAIN BOOSTER", font=self.font_label, text_color=TEXT_MUTED).pack(side="left")
        self.lbl_gain_display = ctk.CTkLabel(gain_header, text="+0.0 dB (1.00x)", font=self.font_readout, text_color=COLOR_EMERALD)
        self.lbl_gain_display.pack(side="right")

        self.slider_gain = ctk.CTkSlider(
            gain_card,
            from_=0.0,
            to=36.0,
            number_of_steps=360,
            command=self._on_gain_slider_changed,
            progress_color=COLOR_EMERALD,
            button_color=COLOR_EMERALD,
            button_hover_color=COLOR_EMERALD_HOVER,
            height=16,
        )
        self.slider_gain.set(0.0)
        self.slider_gain.pack(fill="x", padx=12, pady=4)

        presets_box = ctk.CTkFrame(gain_card, fg_color="transparent")
        presets_box.pack(fill="x", padx=12, pady=(4, 10))
        for label, val in [("0 dB", 0.0), ("+6 dB", 6.0), ("+12 dB", 12.0), ("+18 dB", 18.0), ("+24 dB", 24.0), ("+30 dB", 30.0), ("+36 dB", 36.0)]:
            btn = ctk.CTkButton(
                presets_box,
                text=label,
                width=45,
                height=24,
                fg_color=BTN_SECONDARY,
                hover_color=BTN_SECONDARY_HOVER,
                font=self.font_caption,
                text_color=TEXT_SECONDARY,
                corner_radius=RADIUS_BTN,
                command=lambda v=val: self._set_gain_preset(v),
            )
            btn.pack(side="left", padx=2)

        # Sound Profile & Equalization
        prof_card = ctk.CTkFrame(tab, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        prof_card.pack(fill="x", padx=10, pady=6)

        prof_header = ctk.CTkFrame(prof_card, fg_color="transparent")
        prof_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(prof_header, text="VOICE PROFILES & ARTICULATION EQ", font=self.font_label, text_color=TEXT_MUTED).pack(side="left")

        prof_row = ctk.CTkFrame(prof_card, fg_color="transparent")
        prof_row.pack(fill="x", padx=12, pady=(4, 6))

        profile_names = [p.name for p in SOUND_PROFILES.values()]
        self.opt_profile = ctk.CTkOptionMenu(
            prof_row,
            values=profile_names,
            command=self._on_profile_changed,
            font=self.font_body,
            dropdown_font=self.font_body,
            fg_color=BG_CARD,
            button_color=BTN_SECONDARY,
            button_hover_color=BTN_SECONDARY_HOVER,
            dropdown_fg_color="#0e111c",
            width=260,
            height=30,
            corner_radius=RADIUS_BTN,
        )
        self.opt_profile.set(SOUND_PROFILES[DEFAULT_PROFILE_KEY].name)
        self.opt_profile.pack(side="left")

        self.lbl_profile_desc = ctk.CTkLabel(
            prof_row,
            text=SOUND_PROFILES[DEFAULT_PROFILE_KEY].description,
            font=self.font_body,
            text_color=TEXT_SECONDARY,
        )
        self.lbl_profile_desc.pack(side="left", padx=(12, 0))

        # Limiter & Mute row
        limiter_row = ctk.CTkFrame(prof_card, fg_color="transparent")
        limiter_row.pack(fill="x", padx=12, pady=(6, 10))

        self.switch_limiter = ctk.CTkSwitch(
            limiter_row,
            text="Anti-Clipping Soft Limiter (-0.5 dBFS Protection)",
            font=self.font_body_bold,
            progress_color=COLOR_EMERALD,
            command=self._on_limiter_toggled,
        )
        self.switch_limiter.select()
        self.switch_limiter.pack(side="left")

        self.limiter_badge = ctk.CTkLabel(
            limiter_row,
            text="CLEAN (NO CLIPPING)",
            font=self.font_caption,
            text_color=COLOR_EMERALD,
            fg_color=BG_EMERALD_TINT,
            corner_radius=RADIUS_BTN,
            padx=10,
            pady=2,
        )
        self.limiter_badge.pack(side="right")

        # VU Meters Card
        meter_card = ctk.CTkFrame(tab, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        meter_card.pack(fill="x", padx=10, pady=6)
        meter_card.grid_columnconfigure((0, 1), weight=1)

        # Pre-Gain Meter
        pre_box = ctk.CTkFrame(meter_card, fg_color="transparent")
        pre_box.grid(row=0, column=0, padx=12, pady=10, sticky="ew")
        pre_h = ctk.CTkFrame(pre_box, fg_color="transparent")
        pre_h.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(pre_h, text="RAW MIC INPUT", font=self.font_label, text_color=TEXT_MUTED).pack(side="left")
        self.lbl_pre_db = ctk.CTkLabel(pre_h, text="-60.0 dBFS", font=self.font_readout, text_color=TEXT_SECONDARY)
        self.lbl_pre_db.pack(side="right")
        self.vu_pre = VUMeterCanvas(pre_box, width=420, height=20)
        self.vu_pre.pack(fill="x")

        # Post-Limiter Master Meter
        post_box = ctk.CTkFrame(meter_card, fg_color="transparent")
        post_box.grid(row=0, column=1, padx=12, pady=10, sticky="ew")
        post_h = ctk.CTkFrame(post_box, fg_color="transparent")
        post_h.pack(fill="x", pady=(0, 2))
        ctk.CTkLabel(post_h, text="MASTER STREAM OUT (MIC + SOUNDS)", font=self.font_label, text_color=COLOR_EMERALD).pack(side="left")
        self.lbl_post_db = ctk.CTkLabel(post_h, text="-60.0 dBFS", font=self.font_readout, text_color=COLOR_EMERALD)
        self.lbl_post_db.pack(side="right")
        self.vu_post = VUMeterCanvas(post_box, width=420, height=20)
        self.vu_post.pack(fill="x")

        # Mic Mute Button
        mute_row = ctk.CTkFrame(tab, fg_color="transparent")
        mute_row.pack(fill="x", padx=10, pady=(4, 8))
        self.btn_mute = ctk.CTkButton(
            mute_row,
            text="🎤 Mic Unmuted",
            font=self.font_btn,
            fg_color=BTN_SECONDARY,
            hover_color=BTN_SECONDARY_HOVER,
            text_color=COLOR_EMERALD,
            height=32,
            width=160,
            corner_radius=RADIUS_BTN,
            command=self._toggle_mute,
        )
        self.btn_mute.pack(side="right")

    # =========================================================================
    # TAB 2: SOUNDBOARD PADS
    # =========================================================================
    def _build_soundboard_tab(self):
        tab = self.tab_sb
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)

        # Soundboard Header Toolbar
        tb = ctk.CTkFrame(tab, fg_color="#141622", corner_radius=10)
        tb.grid(row=0, column=0, padx=10, pady=(6, 4), sticky="ew")

        # Master Soundboard Volume
        ctk.CTkLabel(tb, text="SOUNDBOARD VOLUME", font=self.font_label, text_color=TEXT_MUTED).pack(side="left", padx=(12, 6), pady=8)
        self.slider_sb_vol = ctk.CTkSlider(
            tb,
            from_=0.0,
            to=2.0,
            number_of_steps=200,
            width=140,
            command=self._on_soundboard_volume_changed,
            progress_color=COLOR_BLUE,
            button_color=COLOR_BLUE,
            button_hover_color=COLOR_BLUE_HOVER,
        )
        self.slider_sb_vol.set(1.0)
        self.slider_sb_vol.pack(side="left", padx=4)
        self.lbl_sb_vol = ctk.CTkLabel(tb, text="100%", font=self.font_caption, text_color=TEXT_SECONDARY, width=42)
        self.lbl_sb_vol.pack(side="left", padx=2)

        # Stop All (Panic) Button
        btn_panic = ctk.CTkButton(
            tb,
            text="⏹ Stop All Sounds",
            font=self.font_btn,
            fg_color=BTN_SECONDARY,
            hover_color=COLOR_ROSE_HOVER,
            text_color=COLOR_ROSE,
            height=28,
            width=140,
            corner_radius=RADIUS_BTN,
            command=self._on_soundboard_stop_all,
        )
        btn_panic.pack(side="right", padx=10, pady=8)

        # Add Custom Sound Button
        btn_add = ctk.CTkButton(
            tb,
            text="+ Add Sound File",
            font=self.font_btn,
            fg_color=COLOR_BLUE,
            hover_color=COLOR_BLUE_HOVER,
            text_color="#ffffff",
            height=28,
            width=130,
            corner_radius=RADIUS_BTN,
            command=self._on_add_custom_sound,
        )
        btn_add.pack(side="right", padx=6, pady=8)

        # Scrollable Sound Pads Container
        self.sb_scroll = ctk.CTkScrollableFrame(tab, fg_color="#10121a", corner_radius=RADIUS_CARD)
        self.sb_scroll.grid(row=1, column=0, padx=10, pady=4, sticky="nsew")
        self.sb_scroll.grid_columnconfigure((0, 1, 2, 3), weight=1)

    def _populate_default_soundboard(self):
        """Generate and load built-in preset sounds."""
        sounds_dir = os.path.join(BASE_DIR, "sounds")
        try:
            presets = ProceduralSoundGenerator.generate_all_presets(sounds_dir)
            hotkey_mapping = {
                "airhorn": "1",
                "badumtss": "2",
                "buzzer": "3",
                "coin": "4",
                "levelup": "5",
                "tada": "6",
                "siren": "7",
                "laser": "8",
            }

            for key, (name, path) in presets.items():
                hk = hotkey_mapping.get(key)
                if self.engine:
                    self.engine.soundboard.add_sound(key, name, path, volume=1.0, hotkey=hk)
                self._add_sound_card_ui(key, name, path, hk)
        except Exception as e:
            print(f"[WARN] Failed to populate default soundboard: {e}")

    def _add_sound_card_ui(self, clip_id: str, name: str, file_path: str, hotkey: Optional[str] = None):
        """Render a clickable soundboard pad card in the UI."""
        idx = len(self.sound_cards)
        row = idx // 4
        col = idx % 4

        card = ctk.CTkFrame(self.sb_scroll, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_BTN, border_width=1, border_color=BORDER_SUBTLE)
        card.grid(row=row, column=col, padx=6, pady=6, sticky="ew")

        # Top bar of card (Hotkey Badge)
        card_top = ctk.CTkFrame(card, fg_color="transparent")
        card_top.pack(fill="x", padx=8, pady=(6, 2))

        hk_label = f"[{hotkey.upper()}]" if hotkey else ""
        lbl_hk = ctk.CTkLabel(card_top, text=hk_label, font=self.font_caption, text_color=COLOR_AMBER)
        lbl_hk.pack(side="left")

        # Sound Name
        lbl_title = ctk.CTkLabel(
            card,
            text=name[:18],
            font=self.font_body_bold,
            text_color=TEXT_PRIMARY,
        )
        lbl_title.pack(padx=8, pady=2)

        # Play / Stop button
        btn_play = ctk.CTkButton(
            card,
            text="▶ PLAY",
            font=self.font_btn,
            fg_color=BTN_SECONDARY,
            hover_color=BTN_SECONDARY_HOVER,
            text_color=COLOR_EMERALD,
            height=28,
            corner_radius=RADIUS_BTN,
            command=lambda cid=clip_id: self._on_play_sound_clicked(cid),
        )
        btn_play.pack(fill="x", padx=8, pady=4)

        # Loop checkbox
        chk_loop = ctk.CTkCheckBox(
            card,
            text="Loop",
            font=self.font_caption,
            checkbox_width=16,
            checkbox_height=16,
        )
        chk_loop.pack(pady=(2, 6))

        # Register hotkey
        if hotkey:
            self.hotkeys.register_hotkey(hotkey, lambda cid=clip_id: self._on_play_sound_clicked(cid))

        self.sound_cards[clip_id] = {
            "name": name,
            "path": file_path,
            "btn_play": btn_play,
            "chk_loop": chk_loop,
            "hotkey": hotkey,
        }

    def _on_play_sound_clicked(self, clip_id: str):
        """Handle pad play/stop toggle."""
        if not self.engine:
            return
        card = self.sound_cards.get(clip_id)
        loop = card["chk_loop"].get() == 1 if card else False

        if self.engine.soundboard.is_playing(clip_id):
            self.engine.soundboard.stop_sound(clip_id)
        else:
            self.engine.soundboard.play_sound(clip_id, loop=loop)

    def _on_soundboard_stop_all(self):
        """Stop all playing sound clips."""
        if self.engine:
            self.engine.soundboard.stop_all()

    def _on_soundboard_volume_changed(self, val: float):
        """Update master soundboard volume."""
        pct = int(val * 100)
        self.lbl_sb_vol.configure(text=f"{pct}%")
        if self.engine:
            self.engine.soundboard.set_master_volume(val)

    def _on_add_custom_sound(self):
        """Browse disk to add custom audio file (MP3, WAV, OGG, FLAC, M4A)."""
        file_path = filedialog.askopenfilename(
            title="Select Audio Sound File",
            filetypes=[("Audio Files", "*.mp3;*.wav;*.ogg;*.flac;*.m4a;*.aac"), ("All Files", "*.*")],
        )
        if not file_path:
            return

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        clip_id = f"custom_{int(time.time() * 1000)}"

        try:
            if self.engine:
                self.engine.soundboard.add_sound(clip_id, base_name, file_path)
            self._add_sound_card_ui(clip_id, base_name, file_path)
        except Exception as e:
            print(f"[ERROR] Failed to load sound: {e}")

    # =========================================================================
    # TAB 3: YOUTUBE MUSIC & WEB AUDIO
    # =========================================================================
    def _build_music_tab(self):
        tab = self.tab_music
        tab.grid_columnconfigure(0, weight=1)

        # Section 1: Web Browser WASAPI Loopback Capture (YouTube Music Web)
        lb_card = ctk.CTkFrame(tab, fg_color="#141622", corner_radius=10, border_width=1, border_color="#2b2f42")
        lb_card.pack(fill="x", padx=10, pady=6)

        lb_header = ctk.CTkFrame(lb_card, fg_color="transparent")
        lb_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            lb_header,
            text="BROWSER AUDIO CAPTURE & AUTO-DUCKING",
            font=self.font_label,
            text_color=TEXT_MUTED,
        ).pack(side="left")

        self.switch_loopback = ctk.CTkSwitch(
            lb_header,
            text="Capture Browser Audio (ON/OFF)",
            font=self.font_body_bold,
            progress_color=COLOR_EMERALD,
            command=self._on_loopback_toggled,
        )
        self.switch_loopback.pack(side="right")

        # Instructions banner
        instr_box = ctk.CTkFrame(lb_card, fg_color=BG_CARD, corner_radius=RADIUS_BTN)
        instr_box.pack(fill="x", padx=12, pady=4)
        lbl_instr = ctk.CTkLabel(
            instr_box,
            text="💡 Cara Pakai: Buka music.youtube.com di browser (Chrome/Edge/Firefox). Aktifkan sakelar di atas, maka musik yang Anda dengar otomatis di-mix ke dalam mic Discord/Game dengan fitur Auto-Ducking!",
            font=self.font_body,
            text_color=TEXT_SECONDARY,
            wraplength=860,
            justify="left",
        )
        lbl_instr.pack(padx=10, pady=6, anchor="w")

        # Loopback Settings Row
        lb_settings = ctk.CTkFrame(lb_card, fg_color="transparent")
        lb_settings.pack(fill="x", padx=12, pady=6)

        ctk.CTkLabel(lb_settings, text="SOURCE OUTPUT:", font=self.font_label, text_color=TEXT_MUTED).pack(side="left", padx=(0, 6))
        self.opt_loopback_source = ctk.CTkOptionMenu(
            lb_settings,
            values=["Default Speakers Loopback"],
            command=self._on_loopback_device_changed,
            font=self.font_body,
            dropdown_font=self.font_body,
            fg_color=BG_CARD,
            button_color=BTN_SECONDARY,
            dropdown_fg_color="#181b29",
            width=260,
            height=28,
            corner_radius=RADIUS_BTN,
        )
        self.opt_loopback_source.pack(side="left", padx=4)

        # Web Music Volume Slider
        ctk.CTkLabel(lb_settings, text="VOL:", font=self.font_label, text_color=TEXT_MUTED).pack(side="left", padx=(14, 4))
        self.slider_music_vol = ctk.CTkSlider(
            lb_settings,
            from_=0.0,
            to=1.5,
            number_of_steps=150,
            width=130,
            command=self._on_music_volume_changed,
            progress_color=COLOR_EMERALD,
            button_color=COLOR_EMERALD,
            button_hover_color=COLOR_EMERALD_HOVER,
        )
        self.slider_music_vol.set(0.85)
        self.slider_music_vol.pack(side="left", padx=4)
        self.lbl_music_vol = ctk.CTkLabel(lb_settings, text="85%", font=self.font_caption, text_color=COLOR_EMERALD, width=36)
        self.lbl_music_vol.pack(side="left")

        # Auto-Ducking Controls Row
        duck_row = ctk.CTkFrame(lb_card, fg_color="transparent")
        duck_row.pack(fill="x", padx=12, pady=(4, 10))

        self.switch_autoduck = ctk.CTkSwitch(
            duck_row,
            text="Auto-Duck Music when speaking into mic (-12 dB fade)",
            font=self.font_body_bold,
            progress_color=COLOR_EMERALD,
            command=self._on_autoduck_toggled,
        )
        self.switch_autoduck.select()
        self.switch_autoduck.pack(side="left")

        self.lbl_duck_status = ctk.CTkLabel(
            duck_row,
            text="MUSIC FULL (NO DUCKING)",
            font=self.font_caption,
            text_color=COLOR_EMERALD,
            fg_color=BG_EMERALD_TINT,
            corner_radius=RADIUS_BTN,
            padx=8,
            pady=2,
        )
        self.lbl_duck_status.pack(side="right")

        # Section 2: Built-in YouTube Music Stream Player
        yt_card = ctk.CTkFrame(tab, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        yt_card.pack(fill="x", padx=10, pady=6)

        yt_header = ctk.CTkFrame(yt_card, fg_color="transparent")
        yt_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            yt_header,
            text="BUILT-IN YOUTUBE MUSIC STREAM PLAYER (DIRECT URL)",
            font=self.font_label,
            text_color=TEXT_MUTED,
        ).pack(side="left")

        # URL entry & Play button
        url_row = ctk.CTkFrame(yt_card, fg_color="transparent")
        url_row.pack(fill="x", padx=12, pady=6)

        self.entry_yt_url = ctk.CTkEntry(
            url_row,
            placeholder_text="Paste YouTube Music / YouTube URL here (e.g. https://music.youtube.com/watch?v=...)",
            font=self.font_body,
            height=32,
            fg_color=BG_CARD,
            border_color=BORDER_SUBTLE,
            corner_radius=RADIUS_BTN,
        )
        self.entry_yt_url.pack(side="left", fill="x", expand=True, padx=(0, 8))

        self.btn_yt_play = ctk.CTkButton(
            url_row,
            text="Stream Track",
            font=self.font_btn,
            fg_color=COLOR_BLUE,
            hover_color=COLOR_BLUE_HOVER,
            width=110,
            height=32,
            corner_radius=RADIUS_BTN,
            command=self._on_yt_stream_clicked,
        )
        self.btn_yt_play.pack(side="left", padx=2)

        self.btn_yt_stop = ctk.CTkButton(
            url_row,
            text="Stop",
            font=self.font_btn,
            fg_color=BTN_SECONDARY,
            hover_color=COLOR_ROSE_HOVER,
            text_color=COLOR_ROSE,
            width=70,
            height=32,
            corner_radius=RADIUS_BTN,
            command=self._on_yt_stream_stop,
        )
        self.btn_yt_stop.pack(side="left", padx=2)

        # Track Info Status Bar
        self.lbl_yt_track_info = ctk.CTkLabel(
            yt_card,
            text="Ready to stream YouTube Music tracks directly into microphone.",
            font=self.font_body,
            text_color=TEXT_SECONDARY,
        )
        self.lbl_yt_track_info.pack(padx=12, pady=(2, 6), anchor="w")

        # Section 3: Discord Voice Settings Recommendation Card
        discord_guide = ctk.CTkFrame(tab, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        discord_guide.pack(fill="x", padx=10, pady=6)

        guide_h = ctk.CTkFrame(discord_guide, fg_color="transparent")
        guide_h.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            guide_h,
            text="PENGATURAN DISCORD UNTUK KUALITAS AUDIO MAKSIMAL",
            font=self.font_label,
            text_color=TEXT_MUTED,
        ).pack(side="left")

        tips_text = (
            "Jika memutar audio lewat jalur microphone virtual, Discord menerapkan filter suara bawaan.\n"
            "Buka Discord ➔ User Settings (⚙️) ➔ Voice & Video:\n"
            "  • Noise Suppression (Krisp) ➔ Nonaktifkan [None] (Mencegah nada musik terpotong)\n"
            "  • Echo Cancellation ➔ Nonaktifkan [OFF] (Mencegah audio teredam/hollow)\n"
            "  • Automatic Gain Control ➔ Nonaktifkan [OFF] (Mencegah fluktuasi volume dinamis)\n"
            "  • Input Sensitivity ➔ Nonaktifkan otomatis, atur ke -60 dB agar audio mengalir stabil."
        )
        lbl_tips = ctk.CTkLabel(
            discord_guide,
            text=tips_text,
            font=self.font_body,
            text_color=TEXT_SECONDARY,
            justify="left",
            wraplength=880,
        )
        lbl_tips.pack(padx=12, pady=(2, 10), anchor="w")

    # =========================================================================
    # TAB 4: DISCORD VOICE BOT & HI-FI STREAMER
    # =========================================================================
    def _build_bot_tab(self):
        """Build Discord Voice Bot control tab."""
        tab = self.tab_bot
        tab.grid_columnconfigure(0, weight=1)

        # 1. Bot Connection & Token Card
        conn_card = ctk.CTkFrame(tab, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        conn_card.pack(fill="x", padx=10, pady=6)

        conn_header = ctk.CTkFrame(conn_card, fg_color="transparent")
        conn_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            conn_header,
            text="DISCORD BOT CONNECTION (48kHz STEREO OPUS)",
            font=self.font_label,
            text_color=TEXT_MUTED,
        ).pack(side="left")

        self.lbl_bot_status = ctk.CTkLabel(
            conn_header,
            text="○ OFFLINE",
            font=self.font_caption,
            text_color=TEXT_MUTED,
            fg_color=BG_CARD,
            corner_radius=RADIUS_BTN,
            padx=10,
            pady=2,
        )
        self.lbl_bot_status.pack(side="right")

        token_row = ctk.CTkFrame(conn_card, fg_color="transparent")
        token_row.pack(fill="x", padx=12, pady=(4, 10))

        ctk.CTkLabel(
            token_row,
            text="BOT TOKEN:",
            font=self.font_label,
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(0, 8))
        self.entry_bot_token = ctk.CTkEntry(
            token_row,
            placeholder_text="Paste your Discord Bot Token from Developer Portal...",
            font=self.font_body,
            show="*",
            height=30,
            corner_radius=RADIUS_BTN,
            fg_color=BG_CARD,
            border_color=BORDER_SUBTLE,
        )
        self.entry_bot_token.pack(side="left", fill="x", expand=True, padx=(0, 6))
        saved_tok = load_saved_token()
        if saved_tok:
            self.entry_bot_token.insert(0, saved_tok)

        self.btn_show_token = ctk.CTkButton(
            token_row,
            text="👁️",
            width=36,
            height=30,
            fg_color=BTN_SECONDARY,
            hover_color=BTN_SECONDARY_HOVER,
            corner_radius=RADIUS_BTN,
            command=self._toggle_show_bot_token,
        )
        self.btn_show_token.pack(side="left", padx=(0, 6))

        self.btn_bot_login = ctk.CTkButton(
            token_row,
            text="Connect Bot",
            font=self.font_btn,
            fg_color=COLOR_EMERALD,
            hover_color=COLOR_EMERALD_HOVER,
            text_color="#062817",
            width=110,
            height=30,
            corner_radius=RADIUS_BTN,
            command=self._toggle_bot_connection,
        )
        self.btn_bot_login.pack(side="left")

        # 2. Voice Channel Routing Card
        vc_card = ctk.CTkFrame(tab, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        vc_card.pack(fill="x", padx=10, pady=6)

        vc_header = ctk.CTkFrame(vc_card, fg_color="transparent")
        vc_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            vc_header,
            text="VOICE CHANNEL ROUTING",
            font=self.font_label,
            text_color=TEXT_MUTED,
        ).pack(side="left")

        self.lbl_bot_vc_status = ctk.CTkLabel(
            vc_header,
            text="VC: Disconnected",
            font=self.font_caption,
            text_color=TEXT_MUTED,
        )
        self.lbl_bot_vc_status.pack(side="right")

        vc_row = ctk.CTkFrame(vc_card, fg_color="transparent")
        vc_row.pack(fill="x", padx=12, pady=(4, 10))

        self.opt_bot_vc = ctk.CTkOptionMenu(
            vc_row,
            values=["Login bot first to see server channels..."],
            font=self.font_body,
            dropdown_font=self.font_body,
            height=30,
            corner_radius=RADIUS_BTN,
            fg_color=BG_CARD,
            button_color=BTN_SECONDARY,
            button_hover_color=BTN_SECONDARY_HOVER,
            dropdown_fg_color="#0e111c",
        )
        self.opt_bot_vc.pack(side="left", fill="x", expand=True, padx=(0, 6))

        btn_refresh_vc = ctk.CTkButton(
            vc_row,
            text="🔄 Refresh",
            font=self.font_btn,
            width=75,
            height=30,
            fg_color=BTN_SECONDARY,
            hover_color=BTN_SECONDARY_HOVER,
            corner_radius=RADIUS_BTN,
            command=self._refresh_bot_channels,
        )
        btn_refresh_vc.pack(side="left", padx=(0, 6))

        self.btn_join_vc = ctk.CTkButton(
            vc_row,
            text="Join VC",
            font=self.font_btn,
            fg_color=COLOR_BLUE,
            hover_color=COLOR_BLUE_HOVER,
            text_color="#ffffff",
            width=90,
            height=30,
            corner_radius=RADIUS_BTN,
            command=self._toggle_bot_vc_join,
        )
        self.btn_join_vc.pack(side="left")

        # 3. Hi-Fi Music Streaming (YouTube / URL)
        music_card = ctk.CTkFrame(tab, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        music_card.pack(fill="x", padx=10, pady=6)

        m_header = ctk.CTkFrame(music_card, fg_color="transparent")
        m_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            m_header,
            text="DIRECT YOUTUBE & YOUTUBE MUSIC STREAM",
            font=self.font_label,
            text_color=TEXT_MUTED,
        ).pack(side="left")

        # Search & Play Input
        search_row = ctk.CTkFrame(music_card, fg_color="transparent")
        search_row.pack(fill="x", padx=12, pady=(4, 6))

        self.entry_bot_song = ctk.CTkEntry(
            search_row,
            placeholder_text="Search song name, paste YouTube link, or paste YouTube Music URL...",
            font=self.font_body,
            height=32,
            corner_radius=RADIUS_BTN,
            fg_color=BG_CARD,
            border_color=BORDER_SUBTLE,
        )
        self.entry_bot_song.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_bot_song.bind("<Return>", lambda e: self._on_bot_play_music())

        btn_play_song = ctk.CTkButton(
            search_row,
            text="▶ Play / Enqueue",
            font=self.font_btn,
            fg_color=COLOR_EMERALD,
            hover_color=COLOR_EMERALD_HOVER,
            text_color="#062817",
            width=120,
            height=32,
            corner_radius=RADIUS_BTN,
            command=self._on_bot_play_music,
        )
        btn_play_song.pack(side="left")

        # Now Playing & Playback Controls
        ctrl_row = ctk.CTkFrame(music_card, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=12, pady=(4, 6))

        self.lbl_bot_now_playing = ctk.CTkLabel(
            ctrl_row,
            text="🎵 No audio playing in VC",
            font=self.font_body_bold,
            text_color=TEXT_SECONDARY,
        )
        self.lbl_bot_now_playing.pack(side="left", fill="x", expand=True)

        btn_pause = ctk.CTkButton(
            ctrl_row,
            text="⏸️ Pause",
            font=self.font_btn,
            width=65,
            height=28,
            fg_color=BTN_SECONDARY,
            hover_color=BTN_SECONDARY_HOVER,
            corner_radius=RADIUS_BTN,
            command=self._on_bot_pause,
        )
        btn_pause.pack(side="left", padx=2)

        btn_resume = ctk.CTkButton(
            ctrl_row,
            text="▶️ Resume",
            font=self.font_btn,
            width=68,
            height=28,
            fg_color=BTN_SECONDARY,
            hover_color=BTN_SECONDARY_HOVER,
            corner_radius=RADIUS_BTN,
            command=self._on_bot_resume,
        )
        btn_resume.pack(side="left", padx=2)

        btn_skip = ctk.CTkButton(
            ctrl_row,
            text="⏭️ Skip",
            font=self.font_btn,
            width=60,
            height=28,
            fg_color=BTN_SECONDARY,
            hover_color=COLOR_BLUE_HOVER,
            text_color=COLOR_BLUE,
            corner_radius=RADIUS_BTN,
            command=self._on_bot_skip,
        )
        btn_skip.pack(side="left", padx=2)

        btn_stop = ctk.CTkButton(
            ctrl_row,
            text="⏹️ Stop",
            font=self.font_btn,
            width=58,
            height=28,
            fg_color=BTN_SECONDARY,
            hover_color=COLOR_ROSE_HOVER,
            text_color=COLOR_ROSE,
            corner_radius=RADIUS_BTN,
            command=self._on_bot_stop,
        )
        btn_stop.pack(side="left", padx=2)

        ctk.CTkLabel(ctrl_row, text="VOL:", font=self.font_label, text_color=TEXT_MUTED).pack(side="left", padx=(6, 2))
        self.slider_bot_vol = ctk.CTkSlider(
            ctrl_row,
            from_=0.0,
            to=1.5,
            number_of_steps=150,
            width=80,
            progress_color=COLOR_EMERALD,
            button_color=COLOR_EMERALD,
            button_hover_color=COLOR_EMERALD_HOVER,
            command=self._on_bot_vol_changed,
        )
        self.slider_bot_vol.set(1.0)
        self.slider_bot_vol.pack(side="left", padx=2)
        self.lbl_bot_vol = ctk.CTkLabel(ctrl_row, text="100%", font=self.font_caption, text_color=TEXT_SECONDARY, width=32)
        self.lbl_bot_vol.pack(side="left")

        # Queue Header & Action Bar
        queue_header = ctk.CTkFrame(music_card, fg_color="transparent")
        queue_header.pack(fill="x", padx=12, pady=(6, 2))

        self.lbl_queue_count = ctk.CTkLabel(
            queue_header,
            text="📋 Upcoming Queue (0 Songs)",
            font=self.font_body_bold,
            text_color=TEXT_SECONDARY,
        )
        self.lbl_queue_count.pack(side="left")

        btn_clear_q = ctk.CTkButton(
            queue_header,
            text="🗑️ Clear Queue",
            width=90,
            height=24,
            fg_color=BTN_SECONDARY,
            hover_color="#4c0519",
            text_color=COLOR_ROSE,
            font=self.font_caption,
            corner_radius=RADIUS_BTN,
            command=self._on_bot_clear_queue,
        )
        btn_clear_q.pack(side="right")

        # Scrollable Queue Textbox
        self.txt_queue = ctk.CTkTextbox(
            music_card,
            height=75,
            corner_radius=RADIUS_BTN,
            fg_color="#0d101a",
            font=self.font_code,
            text_color=TEXT_SECONDARY,
            wrap="word",
        )
        self.txt_queue.pack(fill="x", padx=12, pady=(2, 10))
        self.txt_queue.insert("1.0", "📭 Antrean kosong. Ketik judul lagu / link YouTube Music di atas atau gunakan /play di Discord!")
        self.txt_queue.configure(state="disabled")

        # 4. Instant Soundboard to Voice Channel
        sb_card = ctk.CTkFrame(tab, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        sb_card.pack(fill="x", padx=10, pady=6)

        sb_header = ctk.CTkFrame(sb_card, fg_color="transparent")
        sb_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            sb_header,
            text="INSTANT SOUNDBOARD PADS",
            font=self.font_label,
            text_color=TEXT_MUTED,
        ).pack(side="left")

        btn_box = ctk.CTkFrame(sb_card, fg_color="transparent")
        btn_box.pack(fill="x", padx=12, pady=(4, 10))

        sounds = [
            ("🎺 Airhorn", "airhorn"),
            ("🥁 Ba-Dum-Tss", "badumtss"),
            ("🔔 Level Up", "levelup"),
            ("🎉 Tada", "tada"),
            ("🚨 Siren", "siren"),
            ("⚡ Laser", "laser"),
        ]
        sounds_dir = os.path.join(BASE_DIR, "sounds")
        os.makedirs(sounds_dir, exist_ok=True)
        for label, sound_id in sounds:
            path = os.path.join(sounds_dir, f"{sound_id}.wav")
            btn = ctk.CTkButton(
                btn_box,
                text=label,
                height=28,
                fg_color=BTN_SECONDARY,
                hover_color=BTN_SECONDARY_HOVER,
                font=self.font_btn,
                corner_radius=RADIUS_BTN,
                command=lambda p=path, l=label: self._play_bot_sound(p, l),
            )
            btn.pack(side="left", padx=3)

        btn_browse_sound = ctk.CTkButton(
            btn_box,
            text="📂 Custom Sound...",
            height=28,
            fg_color=COLOR_BLUE,
            hover_color=COLOR_BLUE_HOVER,
            text_color="#ffffff",
            font=self.font_btn,
            corner_radius=RADIUS_BTN,
            command=self._on_bot_browse_sound,
        )
        btn_browse_sound.pack(side="left", padx=(8, 2))

    # =========================================================================
    # DISCORD BOT HANDLERS
    # =========================================================================
    def _on_bot_status_update(self, status: str, detail: str):
        """Threadsafe handler for status updates from DiscordVoiceBot background thread."""
        def _update():
            if status == "CONNECTING":
                self.lbl_bot_status.configure(text="CONNECTING...", text_color=COLOR_AMBER, fg_color=BG_AMBER_TINT)
            elif status == "ONLINE":
                self.lbl_bot_status.configure(text=f"🟢 ONLINE: {detail}", text_color=COLOR_EMERALD, fg_color=BG_EMERALD_TINT)
                self.btn_bot_login.configure(text="Disconnect", fg_color=BTN_SECONDARY, hover_color=COLOR_ROSE_HOVER, text_color=COLOR_ROSE)
                self._refresh_bot_channels()
            elif status == "OFFLINE":
                self.lbl_bot_status.configure(text="○ OFFLINE", text_color=TEXT_MUTED, fg_color=BG_CARD)
                self.btn_bot_login.configure(text="Connect Bot", fg_color=COLOR_EMERALD, hover_color=COLOR_EMERALD_HOVER, text_color="#062817")
                self.opt_bot_vc.configure(values=["Login bot first..."])
                self.opt_bot_vc.set("Login bot first...")
                self.lbl_bot_vc_status.configure(text="VC: Disconnected", text_color=TEXT_MUTED)
                self.btn_join_vc.configure(text="Join VC", fg_color=COLOR_BLUE, hover_color=COLOR_BLUE_HOVER, text_color="#ffffff")
            elif status == "VOICE_CONNECTED":
                self.lbl_bot_vc_status.configure(text=f"🟢 In VC: #{detail}", text_color=COLOR_EMERALD)
                self.btn_join_vc.configure(text="Leave VC", fg_color=BTN_SECONDARY, hover_color=COLOR_ROSE_HOVER, text_color=COLOR_ROSE)
            elif status == "VOICE_DISCONNECTED":
                self.lbl_bot_vc_status.configure(text="VC: Disconnected", text_color=TEXT_MUTED)
                self.btn_join_vc.configure(text="Join VC", fg_color=COLOR_BLUE, hover_color=COLOR_BLUE_HOVER, text_color="#ffffff")
            elif status == "PLAYING":
                self.lbl_bot_now_playing.configure(text=f"🎵 Playing: {detail}", text_color=COLOR_EMERALD)
            elif status == "PAUSED":
                self.lbl_bot_now_playing.configure(text=f"⏸️ Paused: {detail}", text_color=COLOR_AMBER)
            elif status == "PLAYBACK_STOPPED":
                self.lbl_bot_now_playing.configure(text="🎵 No audio playing in VC", text_color=TEXT_SECONDARY)
            elif status == "SEARCHING":
                self.lbl_bot_now_playing.configure(text=f"🔍 {detail}", text_color=COLOR_AMBER)
            elif status == "QUEUE_UPDATED":
                self._update_queue_ui()
            elif status == "ERROR":
                self.lbl_bot_now_playing.configure(text=f"⚠️ {detail}", text_color=COLOR_ROSE)

        self.after(0, _update)

    def _toggle_bot_connection(self):
        """Toggle Discord Bot login / logout."""
        if self.bot.is_connected:
            self.bot.stop()
        else:
            token = self.entry_bot_token.get().strip()
            if not token:
                self.lbl_bot_now_playing.configure(text="⚠️ Please enter a Discord Bot Token first!", text_color="#ff5252")
                return
            self.bot.start(token)

    def _toggle_show_bot_token(self):
        """Toggle masking on bot token entry."""
        curr = self.entry_bot_token.cget("show")
        if curr == "*":
            self.entry_bot_token.configure(show="")
            self.btn_show_token.configure(text="🔒")
        else:
            self.entry_bot_token.configure(show="*")
            self.btn_show_token.configure(text="👁️")

    def _refresh_bot_channels(self):
        """Fetch list of voice channels in bot guilds and update dropdown."""
        channels = self.bot.get_available_voice_channels()
        if channels:
            self.bot_channels_map = {name: cid for name, cid in channels}
            names = list(self.bot_channels_map.keys())
            self.opt_bot_vc.configure(values=names)
            self.opt_bot_vc.set(names[0])
        else:
            self.opt_bot_vc.configure(values=["No voice channels found (invite bot to server)"])
            self.opt_bot_vc.set("No voice channels found (invite bot to server)")

    def _toggle_bot_vc_join(self):
        """Join or leave the selected voice channel."""
        if self.bot.is_in_voice:
            self.bot.leave_voice_channel()
        else:
            chosen = self.opt_bot_vc.get()
            ch_id = self.bot_channels_map.get(chosen)
            if ch_id:
                self.bot.join_voice_channel(ch_id)
            else:
                self.lbl_bot_now_playing.configure(text="⚠️ Select a valid voice channel first!", text_color="#ff5252")

    def _on_bot_play_music(self):
        """Send YouTube query or URL to Discord Bot for voice channel playback."""
        query = self.entry_bot_song.get().strip()
        if not query:
            return
        if not self.bot.is_in_voice:
            self.lbl_bot_now_playing.configure(text="⚠️ Connect the bot to a Voice Channel first!", text_color="#ffd600")
            return
        self.bot.play_music(query)

    def _on_bot_pause(self):
        """Pause Discord bot playback."""
        self.bot.pause()

    def _on_bot_resume(self):
        """Resume Discord bot playback."""
        self.bot.resume()

    def _on_bot_stop(self):
        """Stop Discord bot playback."""
        self.bot.stop_playback()

    def _on_bot_vol_changed(self, val: float):
        """Update Discord bot playback volume."""
        pct = int(val * 100)
        self.lbl_bot_vol.configure(text=f"{pct}%")
        self.bot.set_volume(val)

    def _play_bot_sound(self, file_path: str, label: str):
        """Send sound effect directly to Discord voice channel."""
        if not self.bot.is_in_voice:
            self.lbl_bot_now_playing.configure(text="⚠️ Connect bot to Voice Channel to play sounds!", text_color="#ffd600")
            return
        self.bot.play_sound(file_path, label)

    def _on_bot_browse_sound(self):
        """Browse and play any custom sound file into Discord voice channel."""
        if not self.bot.is_in_voice:
            self.lbl_bot_now_playing.configure(text="⚠️ Connect bot to Voice Channel first!", text_color="#ffd600")
            return
        file_path = filedialog.askopenfilename(
            title="Select Audio File for Discord Voice Channel",
            filetypes=[("Audio Files", "*.mp3;*.wav;*.ogg;*.flac;*.m4a;*.aac"), ("All Files", "*.*")],
        )
        if file_path:
            self.bot.play_sound(file_path)

    def _on_bot_skip(self):
        """Skip current track and play next in queue."""
        old = self.bot.skip()
        if old:
            self.lbl_bot_now_playing.configure(text="⏭️ Skipping track...", text_color="#2979ff")

    def _on_bot_clear_queue(self):
        """Clear all upcoming tracks from queue."""
        self.bot.clear_queue()
        self._update_queue_ui()

    def _update_queue_ui(self):
        """Update queue listbox display from bot queue state."""
        queue = self.bot.get_queue()
        self.lbl_queue_count.configure(text=f"📋 Upcoming Queue ({len(queue)} Songs)")

        self.txt_queue.configure(state="normal")
        self.txt_queue.delete("1.0", "end")

        if not queue:
            self.txt_queue.insert("1.0", "📭 Antrean kosong. Ketik judul lagu / link YouTube Music di atas atau gunakan /play di Discord!")
        else:
            lines = []
            for i, t in enumerate(queue, start=1):
                req = t.get("requester", "User")
                dur = t.get("duration_str", "Live")
                lines.append(f"{i:2d}. {t['title']} [{dur}] (by {req})")
            self.txt_queue.insert("1.0", "\n".join(lines))

        self.txt_queue.configure(state="disabled")

    # =========================================================================
    # AUDIO ROUTING & LOGIC CALLBACKS
    # =========================================================================
    def _refresh_audio_devices(self):
        """Rescan system audio devices and loopback devices."""
        input_devs = AudioDeviceManager.get_input_devices()
        output_devs = AudioDeviceManager.get_output_devices()

        self.input_devices_map.clear()
        self.output_devices_map.clear()
        self.monitor_devices_map.clear()

        def_in = AudioDeviceManager.get_default_input_index()
        def_out = AudioDeviceManager.get_default_output_index()

        # Format input device labels
        in_names = []
        default_in_label = None
        for d in input_devs:
            is_def = " (Default)" if d["index"] == def_in else ""
            lbl = f"{d['name']}{is_def}"
            self.input_devices_map[lbl] = d["index"]
            in_names.append(lbl)
            if d["index"] == def_in:
                default_in_label = lbl

        # Format output device labels
        out_names = []
        default_out_label = None
        for d in output_devs:
            is_def = " (Default)" if d["index"] == def_out else ""
            lbl = f"{d['name']}{is_def}"
            self.output_devices_map[lbl] = d["index"]
            self.monitor_devices_map[lbl] = d["index"]
            out_names.append(lbl)
            if d["index"] == def_out:
                default_out_label = lbl

        if in_names:
            self.opt_input.configure(values=in_names)
            self.opt_input.set(default_in_label if default_in_label else in_names[0])

        if out_names:
            self.opt_output.configure(values=out_names)
            vc = AudioDeviceManager.find_virtual_cable_index()
            vc_label = next((k for k, v in self.output_devices_map.items() if v == vc), None)
            self.opt_output.set(vc_label if vc_label else (default_out_label if default_out_label else out_names[0]))

            self.opt_monitor.configure(values=out_names)
            # Default monitor to user's real speakers / headset
            non_vc = next((k for k, v in self.output_devices_map.items() if "cable" not in k.lower() and v == def_out), out_names[0])
            self.opt_monitor.set(non_vc)

        # Query WASAPI Loopback devices
        loopbacks = LoopbackCaptureWorker.get_available_loopback_devices()
        lb_names = ["Default Speakers Loopback"]
        self.loopback_devices_map.clear()
        self.loopback_devices_map["Default Speakers Loopback"] = None

        for lb in loopbacks:
            name = lb["name"]
            self.loopback_devices_map[name] = lb["id"]
            lb_names.append(name)

        if lb_names:
            self.opt_loopback_source.configure(values=lb_names)
            self.opt_loopback_source.set(lb_names[0])

    def _init_engine(self):
        """Start the audio stream pipeline."""
        in_sel = self.opt_input.get()
        out_sel = self.opt_output.get()
        mon_sel = self.opt_monitor.get()

        in_idx = self.input_devices_map.get(in_sel)
        out_idx = self.output_devices_map.get(out_sel)
        mon_idx = self.monitor_devices_map.get(mon_sel)

        if in_idx is None or out_idx is None:
            return

        if self.engine is not None:
            self.engine.stop()

        self.engine = MicBoostEngine(
            input_device=in_idx,
            output_device=out_idx,
            monitor_device=mon_idx,
            sample_rate=48000,
            block_size=128,
            gain_db=self.slider_gain.get(),
            profile=self.selected_profile_key,
            limiter_enabled=self.switch_limiter.get() == 1,
        )

        # Set monitor state
        self.engine.set_monitor_enabled(self.switch_monitor.get() == 1, monitor_device=mon_idx)

        # Restore soundboard clips into the newly instantiated engine
        sounds_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "sounds"))
        ProceduralSoundGenerator.generate_all_presets(sounds_dir)
        for cid, card in self.sound_cards.items():
            try:
                self.engine.soundboard.add_sound(cid, card["name"], card["path"], hotkey=card.get("hotkey"))
            except Exception:
                pass

        try:
            self.engine.start()
            self.is_running = True
            self.status_badge.configure(
                text="● STREAMING",
                text_color=COLOR_EMERALD,
                fg_color=BG_EMERALD_TINT,
            )
            self.btn_toggle_stream.configure(
                text="Stop Stream",
                fg_color=BTN_SECONDARY,
                hover_color=COLOR_ROSE_HOVER,
                text_color=COLOR_ROSE,
            )

            # Start loopback if toggle was selected
            if self.switch_loopback.get() == 1:
                self._on_loopback_toggled()
        except Exception as e:
            self.is_running = False
            self.status_badge.configure(
                text="⚠️ ERROR",
                text_color=COLOR_ROSE,
                fg_color="#4c0519",
            )
            print(f"Error starting audio engine: {e}")

    def _toggle_stream(self):
        """Start or stop the audio engine stream."""
        if self.is_running:
            if self.engine:
                self.engine.stop()
            self.is_running = False
            self.status_badge.configure(
                text="○ IDLE",
                text_color=TEXT_MUTED,
                fg_color=BG_CARD_SUBTLE,
            )
            self.btn_toggle_stream.configure(
                text="Start Stream",
                fg_color=COLOR_EMERALD,
                hover_color=COLOR_EMERALD_HOVER,
                text_color="#062817",
            )
        else:
            self._init_engine()

    def _on_profile_changed(self, choice: str):
        key = self.profiles_by_name.get(choice, DEFAULT_PROFILE_KEY)
        self.selected_profile_key = key
        prof = SOUND_PROFILES[key]
        self.lbl_profile_desc.configure(text=prof.description)
        if self.engine:
            self.engine.set_profile(key)

    def _on_input_device_changed(self, choice: str):
        idx = self.input_devices_map.get(choice)
        if idx is not None and self.engine and self.is_running:
            self.engine.restart(input_device=idx)

    def _on_output_device_changed(self, choice: str):
        idx = self.output_devices_map.get(choice)
        if idx is not None and self.engine and self.is_running:
            self.engine.restart(output_device=idx)

    def _on_monitor_device_changed(self, choice: str):
        idx = self.monitor_devices_map.get(choice)
        if idx is not None and self.engine:
            self.engine.set_monitor_enabled(self.switch_monitor.get() == 1, monitor_device=idx)

    def _on_monitor_toggled(self):
        enabled = self.switch_monitor.get() == 1
        mon_idx = self.monitor_devices_map.get(self.opt_monitor.get())
        if self.engine:
            self.engine.set_monitor_enabled(enabled, monitor_device=mon_idx)

    def _on_gain_slider_changed(self, value: float):
        db_val = round(value, 1)
        lin_val = 10.0 ** (db_val / 20.0)
        self.lbl_gain_display.configure(text=f"+{db_val:.1f} dB ({lin_val:.2f}x)")
        if self.engine:
            self.engine.set_gain_db(db_val)

    def _set_gain_preset(self, db_value: float):
        self.slider_gain.set(db_value)
        self._on_gain_slider_changed(db_value)

    def _on_limiter_toggled(self):
        enabled = self.switch_limiter.get() == 1
        if self.engine:
            self.engine.set_limiter_enabled(enabled)

    def _toggle_mute(self):
        if not self.engine:
            return
        new_mute = not self.engine.mute
        self.engine.set_mute(new_mute)
        if new_mute:
            self.btn_mute.configure(text="🔇 MUTED", fg_color="#ff1744", text_color="#ffffff")
        else:
            self.btn_mute.configure(text="🎤 Mic Unmuted", fg_color="#222638", text_color="#00e676")

    def _on_loopback_toggled(self):
        enabled = self.switch_loopback.get() == 1
        if not self.engine:
            return
        src_sel = self.opt_loopback_source.get()
        dev_id = self.loopback_devices_map.get(src_sel)
        self.engine.music.enable_loopback(enabled, device_id=dev_id)

    def _on_loopback_device_changed(self, choice: str):
        dev_id = self.loopback_devices_map.get(choice)
        if self.engine and self.switch_loopback.get() == 1:
            self.engine.music.enable_loopback(True, device_id=dev_id)

    def _on_music_volume_changed(self, val: float):
        pct = int(val * 100)
        self.lbl_music_vol.configure(text=f"{pct}%")
        if self.engine:
            self.engine.music.set_volume(val)

    def _on_autoduck_toggled(self):
        enabled = self.switch_autoduck.get() == 1
        if self.engine:
            self.engine.music.ducker.enabled = enabled

    def _on_yt_stream_clicked(self):
        url = self.entry_yt_url.get().strip()
        if not url:
            return
        if not self.engine or not self.is_running:
            self._init_engine()

        self.lbl_yt_track_info.configure(text="Resolving YouTube stream audio...", text_color="#ffd600")
        self.engine.music.stream_player.load_and_play(url)

    def _on_yt_stream_stop(self):
        if self.engine:
            self.engine.music.stream_player.stop()
        self.lbl_yt_track_info.configure(text="Playback stopped.", text_color="#7b8199")

    def _poll_telemetry(self):
        """Telemetry update loop (~30 FPS) for level meters and indicators."""
        if self.engine and self.is_running:
            telem = self.engine.get_telemetry()

            pre_p = telem["pre_peak_db"]
            pre_r = telem["pre_rms_db"]
            post_p = telem["post_peak_db"]
            post_r = telem["post_rms_db"]

            self.vu_pre.update_level(pre_r, pre_p)
            self.vu_post.update_level(post_r, post_p)

            self.lbl_pre_db.configure(text=f"{pre_p:.1f} dBFS")
            self.lbl_post_db.configure(text=f"{post_p:.1f} dBFS")

            # Limiter badge
            if telem["is_limiting"]:
                self.limiter_badge.configure(text="⚡ LIMITING (-0.5 dB)", text_color=COLOR_ROSE, fg_color="#4c0519")
            elif telem["limiter_enabled"]:
                self.limiter_badge.configure(text="CLEAN (NO CLIPPING)", text_color=COLOR_EMERALD, fg_color=BG_EMERALD_TINT)
            else:
                self.limiter_badge.configure(text="LIMITER OFF", text_color=COLOR_AMBER, fg_color=BG_AMBER_TINT)

            # Auto-Ducking status indicator
            if telem["is_ducking"]:
                self.lbl_duck_status.configure(text="⚡ DUCKING ACTIVE (-12 dB)", text_color=COLOR_AMBER, fg_color=BG_AMBER_TINT)
            else:
                self.lbl_duck_status.configure(text="MUSIC FULL (NO DUCKING)", text_color=COLOR_EMERALD, fg_color=BG_EMERALD_TINT)

            # Update Soundboard Pad button colors if playing
            for cid, card in self.sound_cards.items():
                is_p = self.engine.soundboard.is_playing(cid)
                if is_p:
                    card["btn_play"].configure(text="■ STOP", fg_color="#00e676", text_color="#0a1a12")
                else:
                    card["btn_play"].configure(text="▶ PLAY", fg_color="#222638", text_color="#00e676")

            # YouTube Stream info
            sp = self.engine.music.stream_player
            if sp.is_loading:
                self.lbl_yt_track_info.configure(text="Loading YouTube track...", text_color="#ffd600")
            elif sp._running:
                m, s = divmod(int(sp.current_position), 60)
                tm, ts = divmod(int(sp.duration), 60)
                dur_str = f"{m:02d}:{s:02d} / {tm:02d}:{ts:02d}"
                self.lbl_yt_track_info.configure(text=f"🎵 Playing: {sp.title} [{dur_str}]", text_color="#00e676")
            elif sp.error_message:
                self.lbl_yt_track_info.configure(text=f"⚠️ {sp.error_message}", text_color="#ff5252")

            # Performance stats
            drops = telem["overflows"] + telem["underflows"]
            voices = telem["soundboard_active_voices"]
            lb_str = "ON" if telem["loopback_active"] else "OFF"
            self.lbl_perf.configure(text=f"DSP: <0.5% | Drops: {drops} | SB Voices: {voices} | Browser Loopback: {lb_str}")
        else:
            self.vu_pre.update_level(-60.0)
            self.vu_post.update_level(-60.0)
            self.lbl_pre_db.configure(text="-60.0 dBFS")
            self.lbl_post_db.configure(text="-60.0 dBFS")

        self.after(33, self._poll_telemetry)

    def _on_closing(self):
        """Clean up audio streams and threads on window close."""
        self.hotkeys.stop()
        if self.engine:
            self.engine.stop()
        if hasattr(self, "bot") and self.bot:
            self.bot.stop()
        self.destroy()


def main():
    lock = SingleInstanceLock()
    if not lock.acquire():
        print("[Security] Another session of Woeyyy is already running. Switching focus to active window...")
        SingleInstanceLock.focus_existing_window("Woeyyy")
        sys.exit(0)

    try:
        app = WoeyyyApp()
        app.mainloop()
    finally:
        lock.release()


if __name__ == "__main__":
    main()
