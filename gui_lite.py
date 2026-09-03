"""
Woeyyy Lite - Minimalist Microphone Enhancer & Discord Music Bot
Ultra-compact desktop audio tool focused exclusively on:
1. Low-latency Microphone Boost & Clarity with soft limiter and live VU meters.
2. On-Demand Discord Music Bot with 48kHz Opus playback and queue control.

Features:
- Standard ON/OFF power toggles for all processing (no complex technical jargon).
- Complete state persistence across sessions (.lite_config.json) for devices, gain, and bot settings.
- Resilient device matching by name across Windows hardware ID changes.
"""

import json
import os
import sys
import threading
import time
import tkinter as tk
from typing import Dict, List, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageTk

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from engine.audio_engine import AudioDeviceManager, MicBoostEngine
from engine.profiles import DEFAULT_PROFILE_KEY
from engine.discord_bot import DiscordVoiceBot, load_saved_token, save_token

# CustomTkinter theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Design Tokens (Refactoring UI Dark Mode Palette)
BG_MAIN = "#0b0e17"
BG_CARD = "#131724"
BG_CARD_SUBTLE = "#181d2e"
BORDER_SUBTLE = "#21283d"

COLOR_EMERALD = "#10b981"
BG_EMERALD_TINT = "#064e3b"
COLOR_CYAN = "#06b6d4"
BG_CYAN_TINT = "#083344"
COLOR_ROSE = "#f43f5e"
COLOR_ROSE_HOVER = "#e11d48"
COLOR_AMBER = "#f59e0b"
COLOR_BLUE = "#3b82f6"
COLOR_BLUE_HOVER = "#2563eb"

TEXT_PRIMARY = "#f8fafc"
TEXT_SECONDARY = "#94a3b8"
TEXT_MUTED = "#64748b"

BTN_SECONDARY = "#1c2235"
BTN_SECONDARY_HOVER = "#27304a"

RADIUS_CARD = 10
RADIUS_BTN = 6

CONFIG_FILE = os.path.join(BASE_DIR, ".lite_config.json")


def load_lite_config() -> dict:
    """Load persistent user settings for Woeyyy Lite."""
    defaults = {
        "input_device_name": "",
        "output_device_name": "",
        "mic_enabled": True,
        "gain_db": 12.0,
        "limiter_enabled": True,
        "mute": False,
        "bot_volume": 1.0,
    }
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception as e:
            print(f"[Lite] Notice: could not load config: {e}")
    return defaults


def save_lite_config(cfg: dict):
    """Save persistent user settings for Woeyyy Lite."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[Lite] Notice: could not save config: {e}")


try:
    from tkinter_icons import LucideIcon
except ImportError:
    LucideIcon = None

_ICON_CACHE: Dict[Tuple[str, str, int], ctk.CTkImage] = {}


def get_icon(name: str, color: str = "#94a3b8", size: int = 16) -> Optional[ctk.CTkImage]:
    """Generate sharp, modern vector icon using Lucide icons library."""
    if LucideIcon is None:
        return None
    key = (name, color, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    try:
        icon_obj = LucideIcon(name, color=color, size=size)
        pil_img = icon_obj.to_pil()
        ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=(size, size))
        _ICON_CACHE[key] = ctk_img
        return ctk_img
    except Exception:
        return None


def match_device_by_name(target_name: str, available_devices: List[Dict]) -> Optional[int]:
    """Find device index by name, resilient to Windows PortAudio ID shifts."""
    if not target_name:
        return None
    target_clean = target_name.strip().lower()
    # 1. Exact match
    for d in available_devices:
        if d.get("name", "").strip().lower() == target_clean:
            return d.get("index")
    # 2. Substring match
    for d in available_devices:
        dev_clean = d.get("name", "").strip().lower()
        if target_clean in dev_clean or dev_clean in target_clean:
            return d.get("index")
    return None


class CompactVUMeter(tk.Canvas):
    """Smooth, compact canvas VU meter for live dBFS audio telemetry."""

    def __init__(self, parent, width: int = 190, height: int = 14, **kwargs):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg="#0f121d",
            highlightthickness=0,
            bd=0,
            **kwargs,
        )
        self.meter_width = width
        self.meter_height = height
        self.min_db = -60.0
        self.max_db = 0.0
        self.current_db = -60.0
        self.peak_db = -60.0
        self.peak_hold = 0
        self._draw(-60.0, -60.0)

    def update_level(self, rms_db: float, peak_db: Optional[float] = None):
        self.current_db = max(self.min_db, min(self.max_db, rms_db))
        in_p = rms_db if peak_db is None else peak_db
        if in_p >= self.peak_db:
            self.peak_db = min(self.max_db, in_p)
            self.peak_hold = 12
        else:
            if self.peak_hold > 0:
                self.peak_hold -= 1
            else:
                self.peak_db = max(self.min_db, self.peak_db - 1.8)
        self._draw(self.current_db, self.peak_db)

    def reset(self):
        self._draw(-60.0, -60.0)

    def _db_to_x(self, db: float) -> float:
        clamped = max(self.min_db, min(self.max_db, db))
        norm = (clamped - self.min_db) / (self.max_db - self.min_db)
        return norm * (self.meter_width - 4) + 2

    def _draw(self, rms_db: float, peak_db: float):
        self.delete("all")
        # Track background
        self.create_rectangle(
            1, 1, self.meter_width - 1, self.meter_height - 1,
            outline="#1e2436", width=1, fill="#0f121d"
        )
        fill_x = self._db_to_x(rms_db)
        if fill_x > 2:
            x_green = self._db_to_x(-18.0)
            x_amber = self._db_to_x(-6.0)

            # Green zone
            x1 = min(fill_x, x_green)
            if x1 > 2:
                self.create_rectangle(2, 2, x1, self.meter_height - 2, fill="#10b981", outline="")
            # Amber zone
            if fill_x > x_green:
                x2 = min(fill_x, x_amber)
                self.create_rectangle(x_green, 2, x2, self.meter_height - 2, fill="#f59e0b", outline="")
            # Red zone
            if fill_x > x_amber:
                self.create_rectangle(x_amber, 2, fill_x, self.meter_height - 2, fill="#f43f5e", outline="")

        # Peak hold tick
        px = self._db_to_x(peak_db)
        if px > 3:
            pcol = "#f43f5e" if peak_db > -6.0 else ("#f59e0b" if peak_db > -18.0 else "#38bdf8")
            self.create_line(px, 1, px, self.meter_height - 1, fill=pcol, width=2)


class WoeyyyLiteApp(ctk.CTk):
    """
    Woeyyy Lite Desktop Application.
    Minimalist two-section interface: Mic Enhancer (ON/OFF) + Discord Bot (ON/OFF).
    """

    def __init__(self):
        super().__init__()

        # Load Saved State
        self.cfg = load_lite_config()

        self.title("Woeyyy Lite • Mic Enhancer & Discord Bot")
        self.geometry("520x760")
        self.minsize(500, 720)
        self.configure(fg_color=BG_MAIN)

        # Set Windows AppUserModelID for independent taskbar icon
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("woeyyy.audio.lite.1.0")
        except Exception:
            pass

        # Load Icon
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

        # Typography Scale
        self.font_brand = ctk.CTkFont(family="Segoe UI", size=17, weight="bold")
        self.font_badge = ctk.CTkFont(family="Segoe UI", size=9, weight="bold")
        self.font_section = ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
        self.font_label = ctk.CTkFont(family="Segoe UI", size=10, weight="bold")
        self.font_body = ctk.CTkFont(family="Segoe UI", size=11)
        self.font_body_bold = ctk.CTkFont(family="Segoe UI", size=11, weight="bold")
        self.font_btn = ctk.CTkFont(family="Segoe UI", size=11, weight="bold")
        self.font_caption = ctk.CTkFont(family="Segoe UI", size=10)
        self.font_readout = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")

        # Audio Engine State
        self.engine: Optional[MicBoostEngine] = None
        self.is_mic_on = bool(self.cfg.get("mic_enabled", True))
        self.raw_input_devices: List[Tuple[int, str]] = []
        self.raw_output_devices: List[Tuple[int, str]] = []
        self.input_devices_map: Dict[str, int] = {}
        self.output_devices_map: Dict[str, int] = {}

        # Discord Bot State (Lazy Loaded / On-Demand)
        self.bot: Optional[DiscordVoiceBot] = None
        self.bot_channels_map: Dict[str, int] = {}

        # Build Interface
        self._build_header()
        self._build_mic_card()
        self._build_discord_card()

        # Initialize Mic Engine
        self._init_mic_engine()

        # Telemetry Polling Loop (~30 FPS)
        self._poll_mic_telemetry()

        # Clean Exit Hook
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _persist_config(self):
        """Save current runtime state to persistent config file."""
        save_lite_config(self.cfg)

    def _build_header(self):
        """Header Brand Lockup with Lite badge."""
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        header.pack(fill="x", padx=14, pady=(12, 6))

        box = ctk.CTkFrame(header, fg_color="transparent")
        box.pack(side="left", padx=14, pady=10)

        # Logo
        icon_png_path = os.path.join(BASE_DIR, "assets", "app_icon.png")
        if os.path.exists(icon_png_path):
            try:
                self._logo_img = ctk.CTkImage(
                    light_image=Image.open(icon_png_path),
                    dark_image=Image.open(icon_png_path),
                    size=(32, 32),
                )
                lbl_logo = ctk.CTkLabel(box, image=self._logo_img, text="")
                lbl_logo.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        # Text stack
        vbox = ctk.CTkFrame(box, fg_color="transparent")
        vbox.pack(side="left")

        r1 = ctk.CTkFrame(vbox, fg_color="transparent")
        r1.pack(anchor="w")

        ctk.CTkLabel(r1, text="Woeyyy", font=self.font_brand, text_color=TEXT_PRIMARY).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            r1,
            text="LITE",
            font=self.font_badge,
            text_color=COLOR_EMERALD,
            fg_color=BG_EMERALD_TINT,
            corner_radius=4,
            padx=6,
            pady=1,
        ).pack(side="left")

        ctk.CTkLabel(
            vbox,
            text="Minimalist Mic Enhancer • Discord Music Bot",
            font=self.font_caption,
            text_color=TEXT_MUTED,
        ).pack(anchor="w", pady=(1, 0))

    # =========================================================================
    # SECTION 1: MICROPHONE ENHANCER (ON / OFF)
    # =========================================================================
    def _build_mic_card(self):
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        card.pack(fill="x", padx=14, pady=6)

        # Card Title with Main ON/OFF Power Toggle
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 6))

        icon_mic_card = get_icon("mic", color=TEXT_MUTED, size=15)
        ctk.CTkLabel(
            top, text=" MIC ENHANCER", image=icon_mic_card, compound="left",
            font=self.font_label, text_color=TEXT_MUTED
        ).pack(side="left")

        # Mic Power ON/OFF Toggle
        pwr_box = ctk.CTkFrame(top, fg_color="transparent")
        pwr_box.pack(side="right")

        self.lbl_mic_pwr = ctk.CTkLabel(
            pwr_box,
            text="ON" if self.is_mic_on else "OFF",
            font=self.font_caption,
            text_color=COLOR_EMERALD if self.is_mic_on else TEXT_MUTED,
            width=28,
        )
        self.lbl_mic_pwr.pack(side="right", padx=(4, 0))

        self.switch_mic_pwr = ctk.CTkSwitch(
            pwr_box,
            text="",
            width=40,
            progress_color=COLOR_EMERALD,
            command=self._toggle_mic_power,
        )
        if self.is_mic_on:
            self.switch_mic_pwr.select()
        else:
            self.switch_mic_pwr.deselect()
        self.switch_mic_pwr.pack(side="right")

        # Device Selectors
        dev_row = ctk.CTkFrame(card, fg_color="transparent")
        dev_row.pack(fill="x", padx=14, pady=4)

        # Input Mic
        in_box = ctk.CTkFrame(dev_row, fg_color="transparent")
        in_box.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkLabel(in_box, text="Input Microphone", font=self.font_caption, text_color=TEXT_SECONDARY).pack(anchor="w")
        self.opt_input = ctk.CTkOptionMenu(
            in_box, values=["Loading..."], command=self._on_input_changed,
            font=self.font_caption, dropdown_font=self.font_caption, fg_color=BTN_SECONDARY,
            button_color=BORDER_SUBTLE, height=26, corner_radius=RADIUS_BTN
        )
        self.opt_input.pack(fill="x", pady=(2, 0))

        # Output Cable / Headphones
        out_box = ctk.CTkFrame(dev_row, fg_color="transparent")
        out_box.pack(side="right", fill="x", expand=True, padx=(6, 0))
        ctk.CTkLabel(out_box, text="Output Cable / Audio", font=self.font_caption, text_color=TEXT_SECONDARY).pack(anchor="w")
        self.opt_output = ctk.CTkOptionMenu(
            out_box, values=["Loading..."], command=self._on_output_changed,
            font=self.font_caption, dropdown_font=self.font_caption, fg_color=BTN_SECONDARY,
            button_color=BORDER_SUBTLE, height=26, corner_radius=RADIUS_BTN
        )
        self.opt_output.pack(fill="x", pady=(2, 0))

        # Gain Slider & Presets
        gain_row = ctk.CTkFrame(card, fg_color="transparent")
        gain_row.pack(fill="x", padx=14, pady=(8, 4))

        ctk.CTkLabel(gain_row, text="Voice Boost Gain", font=self.font_caption, text_color=TEXT_SECONDARY).pack(side="left")

        saved_gain = float(self.cfg.get("gain_db", 12.0))
        lin_init = 10.0 ** (saved_gain / 20.0)
        self.lbl_gain = ctk.CTkLabel(gain_row, text=f"+{saved_gain:.1f} dB ({lin_init:.2f}x)", font=self.font_readout, text_color=COLOR_EMERALD)
        self.lbl_gain.pack(side="right")

        self.slider_gain = ctk.CTkSlider(
            card, from_=0.0, to=36.0, number_of_steps=360, command=self._on_gain_changed,
            progress_color=COLOR_EMERALD, button_color="#ffffff", button_hover_color=COLOR_EMERALD, height=14
        )
        self.slider_gain.set(saved_gain)
        self._on_gain_changed(saved_gain)
        self.slider_gain.pack(fill="x", padx=14, pady=4)

        # Preset Buttons, Limiter Switch, and Mute
        act_row = ctk.CTkFrame(card, fg_color="transparent")
        act_row.pack(fill="x", padx=14, pady=6)

        for p_db in [6, 12, 18, 24, 30]:
            ctk.CTkButton(
                act_row, text=f"+{p_db}dB", width=44, height=24, font=self.font_caption,
                fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER, text_color=TEXT_SECONDARY,
                command=lambda val=p_db: self._set_gain(val)
            ).pack(side="left", padx=(0, 3))

        # Mute button
        is_muted = bool(self.cfg.get("mute", False))
        mute_txt = " Muted" if is_muted else " Unmuted"
        mute_col = COLOR_ROSE if is_muted else COLOR_EMERALD
        mute_bg = "#4c0519" if is_muted else BTN_SECONDARY
        mute_ic = get_icon("mic-off" if is_muted else "mic", color=mute_col, size=14)

        self.btn_mute = ctk.CTkButton(
            act_row, text=mute_txt, image=mute_ic, compound="left", width=92, height=24,
            font=self.font_btn, fg_color=mute_bg, hover_color=BTN_SECONDARY_HOVER, text_color=mute_col,
            command=self._toggle_mute
        )
        self.btn_mute.pack(side="right")

        # Soft Limiter Switch
        lim_enabled = bool(self.cfg.get("limiter_enabled", True))
        self.switch_limiter = ctk.CTkSwitch(
            act_row, text="Limiter", font=self.font_caption, progress_color=COLOR_EMERALD,
            command=self._on_limiter_toggled
        )
        if lim_enabled:
            self.switch_limiter.select()
        else:
            self.switch_limiter.deselect()
        self.switch_limiter.pack(side="right", padx=(0, 10))

        # Compact Level Meters
        vu_box = ctk.CTkFrame(card, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_BTN, border_width=1, border_color=BORDER_SUBTLE)
        vu_box.pack(fill="x", padx=14, pady=(6, 12))

        # In meter
        r_in = ctk.CTkFrame(vu_box, fg_color="transparent")
        r_in.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(r_in, text="IN", font=self.font_caption, text_color=TEXT_MUTED, width=24).pack(side="left")
        self.vu_in = CompactVUMeter(r_in, width=340, height=12)
        self.vu_in.pack(side="left", fill="x", expand=True, padx=6)
        self.lbl_in_db = ctk.CTkLabel(r_in, text="-60.0", font=self.font_caption, text_color=TEXT_MUTED, width=42)
        self.lbl_in_db.pack(side="right")

        # Out meter
        r_out = ctk.CTkFrame(vu_box, fg_color="transparent")
        r_out.pack(fill="x", padx=10, pady=(2, 6))
        ctk.CTkLabel(r_out, text="OUT", font=self.font_caption, text_color=COLOR_EMERALD, width=24).pack(side="left")
        self.vu_out = CompactVUMeter(r_out, width=340, height=12)
        self.vu_out.pack(side="left", fill="x", expand=True, padx=6)
        self.lbl_out_db = ctk.CTkLabel(r_out, text="-60.0", font=self.font_caption, text_color=COLOR_EMERALD, width=42)
        self.lbl_out_db.pack(side="right")

    # =========================================================================
    # SECTION 2: DISCORD MUSIC BOT (ON / OFF)
    # =========================================================================
    def _build_discord_card(self):
        card = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=RADIUS_CARD, border_width=1, border_color=BORDER_SUBTLE)
        card.pack(fill="x", padx=14, pady=6)

        # Card Title & Bot Power ON/OFF Toggle
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(10, 6))

        icon_bot_card = get_icon("bot", color=TEXT_MUTED, size=15)
        ctk.CTkLabel(
            top, text=" DISCORD BOT", image=icon_bot_card, compound="left",
            font=self.font_label, text_color=TEXT_MUTED
        ).pack(side="left")

        # Bot ON/OFF Toggle Box
        bot_pwr_box = ctk.CTkFrame(top, fg_color="transparent")
        bot_pwr_box.pack(side="right")

        self.lbl_bot_status = ctk.CTkLabel(
            bot_pwr_box, text="OFF", font=self.font_caption, text_color=TEXT_MUTED, width=28
        )
        self.lbl_bot_status.pack(side="right", padx=(4, 0))

        self.switch_bot_pwr = ctk.CTkSwitch(
            bot_pwr_box, text="", width=40, progress_color=COLOR_BLUE, command=self._toggle_bot_power
        )
        self.switch_bot_pwr.deselect()
        self.switch_bot_pwr.pack(side="right")

        # Token input row
        t_row = ctk.CTkFrame(card, fg_color="transparent")
        t_row.pack(fill="x", padx=14, pady=4)

        saved_tok = load_saved_token()
        self.entry_token = ctk.CTkEntry(
            t_row, placeholder_text="Discord Bot Token", show="*", font=self.font_caption,
            height=28, fg_color=BG_CARD_SUBTLE, border_color=BORDER_SUBTLE
        )
        if saved_tok:
            self.entry_token.insert(0, saved_tok)
        self.entry_token.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_show_token = ctk.CTkButton(
            t_row, text="", image=get_icon("eye", color=TEXT_SECONDARY, size=14), width=28, height=28,
            font=self.font_caption, fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
            command=self._toggle_token_visibility
        )
        self.btn_show_token.pack(side="left")

        # Voice Channel selector & Join
        vc_row = ctk.CTkFrame(card, fg_color="transparent")
        vc_row.pack(fill="x", padx=14, pady=4)

        self.opt_vc = ctk.CTkOptionMenu(
            vc_row, values=["Turn Bot ON to see channels"], font=self.font_caption,
            dropdown_font=self.font_caption, fg_color=BTN_SECONDARY, button_color=BORDER_SUBTLE,
            height=28, corner_radius=RADIUS_BTN
        )
        self.opt_vc.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.btn_join = ctk.CTkButton(
            vc_row, text="Join VC", width=90, height=28, font=self.font_btn, fg_color=BTN_SECONDARY,
            hover_color=BTN_SECONDARY_HOVER, state="disabled", command=self._toggle_bot_join_vc
        )
        self.btn_join.pack(side="right")

        # Song Search / Play Controls
        song_row = ctk.CTkFrame(card, fg_color="transparent")
        song_row.pack(fill="x", padx=14, pady=4)

        self.entry_song = ctk.CTkEntry(
            song_row, placeholder_text="Song title or YouTube link", font=self.font_body,
            height=28, fg_color=BG_CARD_SUBTLE, border_color=BORDER_SUBTLE
        )
        self.entry_song.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.entry_song.bind("<Return>", lambda e: self._on_bot_play())

        self.btn_play = ctk.CTkButton(
            song_row, text=" Play", image=get_icon("play", color="#ffffff", size=12), compound="left",
            width=64, height=28, font=self.font_btn, fg_color=COLOR_EMERALD,
            hover_color="#059669", state="disabled", command=self._on_bot_play
        )
        self.btn_play.pack(side="left", padx=(0, 4))

        self.btn_stop_track = ctk.CTkButton(
            song_row, text="", image=get_icon("square", color=TEXT_SECONDARY, size=12), width=28, height=28,
            font=self.font_btn, fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
            state="disabled", command=self._on_bot_stop
        )
        self.btn_stop_track.pack(side="left", padx=(0, 4))

        self.btn_skip = ctk.CTkButton(
            song_row, text="", image=get_icon("skip-forward", color=TEXT_SECONDARY, size=12), width=28, height=28,
            font=self.font_btn, fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER,
            state="disabled", command=self._on_bot_skip
        )
        self.btn_skip.pack(side="right")

        # Status & Volume bar
        stat_bar = ctk.CTkFrame(card, fg_color=BG_CARD_SUBTLE, corner_radius=RADIUS_BTN, border_width=1, border_color=BORDER_SUBTLE)
        stat_bar.pack(fill="x", padx=14, pady=(6, 12))

        self.lbl_now_playing = ctk.CTkLabel(
            stat_bar, text=" Idle (Bot is OFF)", image=get_icon("circle-stop", color=TEXT_MUTED, size=14),
            compound="left", font=self.font_caption, text_color=TEXT_MUTED
        )
        self.lbl_now_playing.pack(side="left", padx=10, pady=6)

        vol_box = ctk.CTkFrame(stat_bar, fg_color="transparent")
        vol_box.pack(side="right", padx=10)

        # Volume icon
        ctk.CTkLabel(vol_box, text="", image=get_icon("volume-2", color=TEXT_MUTED, size=13)).pack(side="left", padx=(0, 2))

        saved_vol = float(self.cfg.get("bot_volume", 1.0))
        self.lbl_bot_vol = ctk.CTkLabel(vol_box, text=f"{int(saved_vol * 100)}%", font=self.font_caption, text_color=TEXT_MUTED, width=32)
        self.lbl_bot_vol.pack(side="right")

        self.slider_bot_vol = ctk.CTkSlider(
            vol_box, from_=0.0, to=1.0, width=70, height=12, number_of_steps=100,
            progress_color=COLOR_BLUE, command=self._on_bot_vol_changed
        )
        self.slider_bot_vol.set(saved_vol)
        self.slider_bot_vol.pack(side="right", padx=4)

    # =========================================================================
    # AUDIO ENGINE LOGIC & PERSISTENCE
    # =========================================================================
    def _init_mic_engine(self):
        try:
            self.raw_input_devices = AudioDeviceManager.get_input_devices()
            self.raw_output_devices = AudioDeviceManager.get_output_devices()

            def_in = AudioDeviceManager.get_default_input_index()
            def_out = AudioDeviceManager.get_default_output_index()

            self.input_devices_map.clear()
            self.output_devices_map.clear()

            # Format input device labels
            for d in self.raw_input_devices:
                d_idx = d.get("index")
                d_name = d.get("name", "Unknown")
                is_def = " (Default)" if d_idx == def_in else ""
                lbl = f"{d_name}{is_def}"
                self.input_devices_map[lbl] = d_idx

            # Format output device labels
            for d in self.raw_output_devices:
                d_idx = d.get("index")
                d_name = d.get("name", "Unknown")
                is_def = " (Default)" if d_idx == def_out else ""
                lbl = f"{d_name}{is_def}"
                self.output_devices_map[lbl] = d_idx

            in_keys = list(self.input_devices_map.keys())
            out_keys = list(self.output_devices_map.keys())

            # 1. Match Saved Input Device by Name
            saved_in_name = self.cfg.get("input_device_name", "")
            matched_in_idx = match_device_by_name(saved_in_name, self.raw_input_devices)
            if matched_in_idx is None and def_in is not None:
                matched_in_idx = def_in

            chosen_in_key = in_keys[0] if in_keys else None
            if matched_in_idx is not None:
                for k, v in self.input_devices_map.items():
                    if v == matched_in_idx:
                        chosen_in_key = k
                        break

            # 2. Match Saved Output Device by Name
            saved_out_name = self.cfg.get("output_device_name", "")
            matched_out_idx = match_device_by_name(saved_out_name, self.raw_output_devices)
            if matched_out_idx is None and def_out is not None:
                matched_out_idx = def_out

            chosen_out_key = out_keys[0] if out_keys else None
            if matched_out_idx is not None:
                for k, v in self.output_devices_map.items():
                    if v == matched_out_idx:
                        chosen_out_key = k
                        break

            if in_keys:
                self.opt_input.configure(values=in_keys)
                if chosen_in_key:
                    self.opt_input.set(chosen_in_key)

            if out_keys:
                self.opt_output.configure(values=out_keys)
                if chosen_out_key:
                    self.opt_output.set(chosen_out_key)

            # Instantiate Engine with restored parameters
            in_id = self.input_devices_map.get(chosen_in_key) if chosen_in_key else None
            out_id = self.output_devices_map.get(chosen_out_key) if chosen_out_key else None

            self.engine = MicBoostEngine(
                input_device=in_id,
                output_device=out_id,
                gain_db=float(self.cfg.get("gain_db", 12.0)),
                profile=DEFAULT_PROFILE_KEY,
                limiter_enabled=bool(self.cfg.get("limiter_enabled", True)),
            )

            # Restore Mute state
            if self.cfg.get("mute", False):
                self.engine.set_mute(True)

            # Start only if mic_enabled was saved as True
            if self.is_mic_on:
                self.engine.start()

        except Exception as e:
            print(f"[Lite] Failed to initialize MicBoostEngine: {e}")

    def _toggle_mic_power(self):
        """Toggle Mic Boost audio processing ON / OFF."""
        self.is_mic_on = self.switch_mic_pwr.get() == 1
        self.cfg["mic_enabled"] = self.is_mic_on
        self._persist_config()

        if self.is_mic_on:
            self.lbl_mic_pwr.configure(text="ON", text_color=COLOR_EMERALD)
            if self.engine and not self.engine.is_running:
                self.engine.start()
        else:
            self.lbl_mic_pwr.configure(text="OFF", text_color=TEXT_MUTED)
            if self.engine and self.engine.is_running:
                self.engine.stop()
            self.vu_in.reset()
            self.vu_out.reset()
            self.lbl_in_db.configure(text="-60.0")
            self.lbl_out_db.configure(text="-60.0")

    def _on_input_changed(self, choice: str):
        idx = self.input_devices_map.get(choice)
        if idx is not None:
            # Save device name for next session
            for d in self.raw_input_devices:
                if d.get("index") == idx:
                    self.cfg["input_device_name"] = d.get("name")
                    self._persist_config()
                    break

            if self.engine and self.is_mic_on:
                self.engine.restart(input_device=idx)

    def _on_output_changed(self, choice: str):
        idx = self.output_devices_map.get(choice)
        if idx is not None:
            # Save device name for next session
            for d in self.raw_output_devices:
                if d.get("index") == idx:
                    self.cfg["output_device_name"] = d.get("name")
                    self._persist_config()
                    break

            if self.engine and self.is_mic_on:
                self.engine.restart(output_device=idx)

    def _on_gain_changed(self, val: float):
        db_val = round(val, 1)
        lin = 10.0 ** (db_val / 20.0)

        # Dynamic color feedback: Emerald (clean), Amber (strong), Rose (extreme)
        if db_val >= 28.0:
            val_color = COLOR_ROSE
        elif db_val >= 18.0:
            val_color = COLOR_AMBER
        else:
            val_color = COLOR_EMERALD

        self.lbl_gain.configure(text=f"+{db_val:.1f} dB ({lin:.2f}x)", text_color=val_color)
        self.slider_gain.configure(progress_color=val_color)
        self.cfg["gain_db"] = db_val
        self._persist_config()

        if self.engine:
            self.engine.set_gain_db(db_val)

    def _set_gain(self, db_value: float):
        self.slider_gain.set(db_value)
        self._on_gain_changed(db_value)

    def _toggle_mute(self):
        if not self.engine:
            return
        new_m = not self.engine.mute
        self.engine.set_mute(new_m)
        self.cfg["mute"] = new_m
        self._persist_config()

        if new_m:
            self.btn_mute.configure(
                text=" Muted", image=get_icon("mic-off", color=COLOR_ROSE, size=14),
                compound="left", text_color=COLOR_ROSE, fg_color="#4c0519"
            )
        else:
            self.btn_mute.configure(
                text=" Unmuted", image=get_icon("mic", color=COLOR_EMERALD, size=14),
                compound="left", text_color=COLOR_EMERALD, fg_color=BTN_SECONDARY
            )

    def _on_limiter_toggled(self):
        en = self.switch_limiter.get() == 1
        self.cfg["limiter_enabled"] = en
        self._persist_config()

        if self.engine:
            self.engine.set_limiter_enabled(en)

    def _poll_mic_telemetry(self):
        if self.engine and self.is_mic_on and self.engine.is_running:
            try:
                telem = self.engine.get_telemetry()
                pre_r = telem["pre_rms_db"]
                pre_p = telem["pre_peak_db"]
                post_r = telem["post_rms_db"]
                post_p = telem["post_peak_db"]

                self.vu_in.update_level(pre_r, pre_p)
                self.vu_out.update_level(post_r, post_p)

                self.lbl_in_db.configure(text=f"{pre_p:.1f}")
                self.lbl_out_db.configure(text=f"{post_p:.1f}")
            except Exception:
                pass

        self.after(33, self._poll_mic_telemetry)

    # =========================================================================
    # DISCORD BOT LOGIC (ON / OFF)
    # =========================================================================
    def _toggle_token_visibility(self):
        if self.entry_token.cget("show") == "*":
            self.entry_token.configure(show="")
            self.btn_show_token.configure(image=get_icon("eye-off", color=TEXT_SECONDARY, size=14))
        else:
            self.entry_token.configure(show="*")
            self.btn_show_token.configure(image=get_icon("eye", color=TEXT_SECONDARY, size=14))

    def _toggle_bot_power(self):
        """Turn Discord Bot ON / OFF."""
        turn_on = self.switch_bot_pwr.get() == 1

        if turn_on:
            tok = self.entry_token.get().strip()
            if not tok:
                self.switch_bot_pwr.deselect()
                self.lbl_now_playing.configure(
                    text=" Please enter a Discord Bot Token!",
                    image=get_icon("circle-alert", color=COLOR_ROSE, size=14),
                    compound="left", text_color=COLOR_ROSE
                )
                return

            save_token(tok)

            if self.bot is None:
                self.bot = DiscordVoiceBot(on_status_change=self._on_bot_status)

            self.lbl_bot_status.configure(text="CONNECTING...", text_color=COLOR_AMBER)
            self.lbl_now_playing.configure(
                text=" Connecting to Discord Gateway...",
                image=get_icon("radio", color=COLOR_AMBER, size=14),
                compound="left", text_color=COLOR_AMBER
            )
            self.bot.start(tok)
            self.bot.set_volume(float(self.cfg.get("bot_volume", 1.0)))
        else:
            if self.bot and self.bot.is_connected:
                self.bot.stop()
            self.lbl_bot_status.configure(text="OFF", text_color=TEXT_MUTED)
            self.btn_join.configure(state="disabled", text="Join VC", fg_color=BTN_SECONDARY)
            self.btn_play.configure(state="disabled")
            self.btn_stop_track.configure(state="disabled")
            self.btn_skip.configure(state="disabled")
            self.lbl_now_playing.configure(
                text=" Idle (Bot is OFF)",
                image=get_icon("circle-stop", color=TEXT_MUTED, size=14),
                compound="left", text_color=TEXT_MUTED
            )

    def _on_bot_status(self, status: str, detail: str):
        def _apply():
            if status in ("ONLINE", "CONNECTED"):
                self.lbl_bot_status.configure(text="ON", text_color=COLOR_EMERALD)
                self.lbl_now_playing.configure(
                    text=f" Logged in as: {detail}",
                    image=get_icon("circle-check", color=COLOR_EMERALD, size=14),
                    compound="left", text_color=COLOR_EMERALD
                )
                self._refresh_voice_channels()
                self.btn_join.configure(state="normal")
            elif status in ("DISCONNECTED", "OFFLINE"):
                self.switch_bot_pwr.deselect()
                self.lbl_bot_status.configure(text="OFF", text_color=TEXT_MUTED)
                self.lbl_now_playing.configure(
                    text=" Bot disconnected",
                    image=get_icon("circle-stop", color=TEXT_MUTED, size=14),
                    compound="left", text_color=TEXT_MUTED
                )
                self.btn_join.configure(state="disabled", text="Join VC", fg_color=BTN_SECONDARY)
                self.btn_play.configure(state="disabled")
                self.btn_stop_track.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
            elif status == "VOICE_CONNECTED":
                self.btn_join.configure(text="Leave VC", fg_color=COLOR_ROSE, hover_color=COLOR_ROSE_HOVER)
                self.btn_play.configure(state="normal")
                self.btn_stop_track.configure(state="normal")
                self.btn_skip.configure(state="normal")
                self.lbl_now_playing.configure(
                    text=f" In VC: #{detail}",
                    image=get_icon("radio", color=COLOR_CYAN, size=14),
                    compound="left", text_color=COLOR_CYAN
                )
            elif status == "VOICE_DISCONNECTED":
                self.btn_join.configure(text="Join VC", fg_color=BTN_SECONDARY, hover_color=BTN_SECONDARY_HOVER)
                self.btn_play.configure(state="disabled")
                self.btn_stop_track.configure(state="disabled")
                self.btn_skip.configure(state="disabled")
                self.lbl_now_playing.configure(
                    text=" Left voice channel",
                    image=get_icon("circle-stop", color=TEXT_MUTED, size=14),
                    compound="left", text_color=TEXT_MUTED
                )
            elif status == "PLAYING":
                self.lbl_now_playing.configure(
                    text=f" Playing: {detail}",
                    image=get_icon("music", color=COLOR_EMERALD, size=14),
                    compound="left", text_color=COLOR_EMERALD
                )
            elif status == "PAUSED":
                self.lbl_now_playing.configure(
                    text=f" Paused: {detail}",
                    image=get_icon("pause", color=COLOR_AMBER, size=14),
                    compound="left", text_color=COLOR_AMBER
                )
            elif status == "PLAYBACK_STOPPED":
                self.lbl_now_playing.configure(
                    text=" Idle (Playback finished)",
                    image=get_icon("circle-stop", color=TEXT_SECONDARY, size=14),
                    compound="left", text_color=TEXT_SECONDARY
                )
            elif status == "SEARCHING":
                self.lbl_now_playing.configure(
                    text=f" {detail}",
                    image=get_icon("music", color=COLOR_AMBER, size=14),
                    compound="left", text_color=COLOR_AMBER
                )
            elif status == "ERROR":
                self.lbl_now_playing.configure(
                    text=f" {detail}",
                    image=get_icon("circle-alert", color=COLOR_ROSE, size=14),
                    compound="left", text_color=COLOR_ROSE
                )
        self.after(0, _apply)

    def _refresh_voice_channels(self):
        if not self.bot:
            return
        chans = self.bot.get_available_voice_channels()
        if chans:
            self.bot_channels_map = {name: cid for name, cid in chans}
            names = list(self.bot_channels_map.keys())
            self.opt_vc.configure(values=names)
            self.opt_vc.set(names[0])
        else:
            self.opt_vc.configure(values=["No voice channels found"])
            self.opt_vc.set("No voice channels found")

    def _toggle_bot_join_vc(self):
        if not self.bot:
            return
        if self.bot.is_in_voice:
            self.bot.leave_voice_channel()
        else:
            chosen = self.opt_vc.get()
            cid = self.bot_channels_map.get(chosen)
            if cid:
                self.bot.join_voice_channel(cid)

    def _on_bot_play(self):
        if not self.bot or not self.bot.is_in_voice:
            self.lbl_now_playing.configure(
                text=" Join a Voice Channel first!",
                image=get_icon("circle-alert", color=COLOR_AMBER, size=14),
                compound="left", text_color=COLOR_AMBER
            )
            return
        q = self.entry_song.get().strip()
        if q:
            self.bot.play_music(q)
            self.entry_song.delete(0, "end")

    def _on_bot_stop(self):
        if self.bot:
            self.bot.stop_playback()

    def _on_bot_skip(self):
        if self.bot:
            self.bot.skip()

    def _on_bot_vol_changed(self, val: float):
        pct = int(val * 100)
        self.lbl_bot_vol.configure(text=f"{pct}%")
        self.cfg["bot_volume"] = val
        self._persist_config()

        if self.bot:
            self.bot.set_volume(val)

    def _on_closing(self):
        try:
            if self.engine:
                self.engine.stop()
            if self.bot and self.bot.is_connected:
                self.bot.stop()
        except Exception:
            pass
        self.destroy()


def main():
    app = WoeyyyLiteApp()
    app.mainloop()


if __name__ == "__main__":
    main()
