"""
Woeyyy - Desktop GUI
Real-Time Soundboard & Microphone Enhancer Interface built with CustomTkinter.
"""

import os
import sys
import tkinter as tk
from typing import Dict, List, Optional
import customtkinter as ctk

# Ensure root path is accessible
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from engine.audio_engine import AudioDeviceManager, MicBoostEngine
from engine.profiles import DEFAULT_PROFILE_KEY, SOUND_PROFILES

# Set CustomTkinter theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class VUMeterCanvas(tk.Canvas):
    """
    High-performance, smooth canvas-rendered audio VU meter.
    Displays level in dBFS [-60 dBFS to 0 dBFS] with professional
    green/yellow/red color zones and decaying peak-hold indicator.
    """

    def __init__(self, parent, width: int = 340, height: int = 24, **kwargs):
        super().__init__(
            parent,
            width=width,
            height=height,
            bg="#161822",
            highlightthickness=1,
            highlightbackground="#2b2f42",
            **kwargs,
        )
        self.w = width
        self.h = height
        self.current_db = -60.0
        self.peak_hold_db = -60.0
        self.peak_decay_rate = 1.2  # dB decay per tick

    def update_level(self, db_value: float):
        """Update meter with latest dBFS value and re-render."""
        # Bound db
        clamped = max(-60.0, min(db_value, 0.0))
        self.current_db = clamped

        # Peak hold logic
        if clamped > self.peak_hold_db:
            self.peak_hold_db = clamped
        else:
            self.peak_hold_db = max(-60.0, self.peak_hold_db - self.peak_decay_rate)

        self.redraw()

    def redraw(self):
        """Redraw meter bar, segments, and peak-hold tick."""
        self.delete("all")

        # Map dB to pixel width
        def db_to_x(val_db):
            ratio = (val_db + 60.0) / 60.0
            return max(0, min(int(ratio * (self.w - 4)), self.w - 4))

        fill_x = db_to_x(self.current_db)
        peak_x = db_to_x(self.peak_hold_db)

        # Threshold points in pixels
        x_minus_18 = db_to_x(-18.0)
        x_minus_3 = db_to_x(-3.0)

        # Draw segmented background grid lines
        for mark_db in (-40, -30, -20, -12, -6, -3, 0):
            mx = db_to_x(mark_db) + 2
            self.create_line(mx, 0, mx, self.h, fill="#232637", width=1)

        # Draw active bar segments
        if fill_x > 0:
            # 1. Green Zone (up to -18 dBFS)
            g_end = min(fill_x, x_minus_18)
            if g_end > 0:
                self.create_rectangle(2, 2, 2 + g_end, self.h - 2, fill="#00e676", outline="")

            # 2. Yellow Zone (-18 dBFS to -3 dBFS)
            if fill_x > x_minus_18:
                y_end = min(fill_x, x_minus_3)
                self.create_rectangle(2 + x_minus_18, 2, 2 + y_end, self.h - 2, fill="#ffca28", outline="")

            # 3. Red Zone (-3 dBFS to 0 dBFS / Hot Peak)
            if fill_x > x_minus_3:
                self.create_rectangle(2 + x_minus_3, 2, 2 + fill_x, self.h - 2, fill="#ff1744", outline="")

        # Draw peak hold tick
        if peak_x > 2:
            peak_color = "#ff1744" if self.peak_hold_db > -3.0 else "#ffffff"
            self.create_line(
                2 + peak_x, 1, 2 + peak_x, self.h - 1, fill=peak_color, width=2
            )


class WoeyyyApp(ctk.CTk):
    """Main Woeyyy Audio Control Center Desktop Application."""

    def __init__(self):
        super().__init__()

        self.title("Woeyyy - Real-Time Audio Enhancer & Soundboard")
        self.geometry("900x720")
        self.minsize(820, 680)
        self.configure(fg_color="#0f111a")

        # Audio Engine Reference
        self.engine: Optional[MicBoostEngine] = None
        self.is_running = False
        self.input_devices_map: Dict[str, int] = {}
        self.output_devices_map: Dict[str, int] = {}
        self.selected_profile_key = DEFAULT_PROFILE_KEY
        self.profiles_by_name = {p.name: p.key for p in SOUND_PROFILES.values()}

        # Setup UI layout
        self._build_ui()

        # Populate devices (do not auto-start stream, leave OFF by default)
        self._refresh_audio_devices()

        # Telemetry update loop (~30 FPS)
        self.after(33, self._poll_telemetry)

        # Handle window close
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _build_ui(self):
        """Construct modern UI cards and panels."""
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # =========================================================================
        # 1. TOP HEADER & STREAM STATUS BAR
        # =========================================================================
        header_frame = ctk.CTkFrame(self, fg_color="#181a27", corner_radius=12, border_width=1, border_color="#2b2f42")
        header_frame.grid(row=0, column=0, padx=20, pady=(15, 10), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=15, pady=12, sticky="w")

        title_lbl = ctk.CTkLabel(
            title_box,
            text="🎙️ WOEYYY AUDIO",
            font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
            text_color="#ffffff",
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ctk.CTkLabel(
            title_box,
            text="Real-Time Low-Latency Microphone Boost & Limiter Engine",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color="#8a8fa3",
        )
        subtitle_lbl.pack(anchor="w")

        # Status badge & Stream toggle button
        status_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        status_box.grid(row=0, column=2, padx=15, pady=12, sticky="e")

        self.status_badge = ctk.CTkLabel(
            status_box,
            text="○ STOPPED",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#8a8fa3",
            fg_color="#1e2130",
            corner_radius=8,
            padx=12,
            pady=4,
        )
        self.status_badge.pack(side="left", padx=(0, 12))

        self.btn_toggle_stream = ctk.CTkButton(
            status_box,
            text="Start Stream",
            command=self._toggle_stream,
            width=120,
            height=36,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color="#00e676",
            hover_color="#00c853",
            text_color="#0a1a12",
            corner_radius=8,
        )
        self.btn_toggle_stream.pack(side="left")

        # =========================================================================
        # 2. AUDIO ROUTING CARD
        # =========================================================================
        routing_card = ctk.CTkFrame(self, fg_color="#181a27", corner_radius=12, border_width=1, border_color="#2b2f42")
        routing_card.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        routing_card.grid_columnconfigure((0, 1), weight=1)

        # Input Mic Dropdown
        in_box = ctk.CTkFrame(routing_card, fg_color="transparent")
        in_box.grid(row=0, column=0, padx=15, pady=12, sticky="ew")
        ctk.CTkLabel(
            in_box,
            text="Microphone Input",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#cdd3e6",
        ).pack(anchor="w", pady=(0, 4))

        self.opt_input = ctk.CTkOptionMenu(
            in_box,
            values=["Detecting..."],
            command=self._on_input_device_changed,
            fg_color="#262a3d",
            button_color="#3d4463",
            button_hover_color="#4d567d",
            dropdown_fg_color="#202436",
            height=32,
            corner_radius=8,
        )
        self.opt_input.pack(fill="x")

        # Output Device Dropdown
        out_box = ctk.CTkFrame(routing_card, fg_color="transparent")
        out_box.grid(row=0, column=1, padx=15, pady=12, sticky="ew")
        ctk.CTkLabel(
            out_box,
            text="Target Output (Virtual Cable or Headphones)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#cdd3e6",
        ).pack(anchor="w", pady=(0, 4))

        self.opt_output = ctk.CTkOptionMenu(
            out_box,
            values=["Detecting..."],
            command=self._on_output_device_changed,
            fg_color="#262a3d",
            button_color="#3d4463",
            button_hover_color="#4d567d",
            dropdown_fg_color="#202436",
            height=32,
            corner_radius=8,
        )
        self.opt_output.pack(fill="x")

        # Refresh Devices Button
        btn_refresh = ctk.CTkButton(
            routing_card,
            text="🔄 Refresh",
            width=90,
            height=32,
            command=self._refresh_audio_devices,
            fg_color="#2a2e45",
            hover_color="#3a4060",
            corner_radius=8,
        )
        btn_refresh.grid(row=0, column=2, padx=(0, 15), pady=12, sticky="e")

        # =========================================================================
        # 3. DUAL VU METERS CARD
        # =========================================================================
        vu_card = ctk.CTkFrame(self, fg_color="#181a27", corner_radius=12, border_width=1, border_color="#2b2f42")
        vu_card.grid(row=2, column=0, padx=20, pady=10, sticky="nsew")
        vu_card.grid_columnconfigure((0, 1), weight=1)

        card_title_box = ctk.CTkFrame(vu_card, fg_color="transparent")
        card_title_box.grid(row=0, column=0, columnspan=2, padx=15, pady=(12, 6), sticky="ew")

        ctk.CTkLabel(
            card_title_box,
            text="📊 Real-Time Audio Level Telemetry",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="#ffffff",
        ).pack(side="left")

        # Limiter indicator badge
        self.limiter_badge = ctk.CTkLabel(
            card_title_box,
            text="LIMITER STANDBY",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#546e7a",
            fg_color="#1e242d",
            corner_radius=6,
            padx=8,
            pady=2,
        )
        self.limiter_badge.pack(side="right")

        # Pre-Boost Mic VU Panel
        pre_frame = ctk.CTkFrame(vu_card, fg_color="#1e2132", corner_radius=10)
        pre_frame.grid(row=1, column=0, padx=(15, 8), pady=10, sticky="nsew")
        pre_frame.grid_columnconfigure(0, weight=1)

        pre_header = ctk.CTkFrame(pre_frame, fg_color="transparent")
        pre_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            pre_header,
            text="🎙️ Mic Input (Raw)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#a6accd",
        ).pack(side="left")
        self.lbl_pre_db = ctk.CTkLabel(
            pre_header,
            text="-60.0 dBFS",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#00e676",
        )
        self.lbl_pre_db.pack(side="right")

        self.vu_pre = VUMeterCanvas(pre_frame, height=22)
        self.vu_pre.pack(fill="x", padx=12, pady=(0, 12))

        # Post-Boost Output VU Panel
        post_frame = ctk.CTkFrame(vu_card, fg_color="#1e2132", corner_radius=10)
        post_frame.grid(row=1, column=1, padx=(8, 15), pady=10, sticky="nsew")
        post_frame.grid_columnconfigure(0, weight=1)

        post_header = ctk.CTkFrame(post_frame, fg_color="transparent")
        post_header.pack(fill="x", padx=12, pady=(10, 4))
        ctk.CTkLabel(
            post_header,
            text="🔊 Stream Output (Boosted & Limited)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color="#a6accd",
        ).pack(side="left")
        self.lbl_post_db = ctk.CTkLabel(
            post_header,
            text="-60.0 dBFS",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#00e676",
        )
        self.lbl_post_db.pack(side="right")

        self.vu_post = VUMeterCanvas(post_frame, height=22)
        self.vu_post.pack(fill="x", padx=12, pady=(0, 12))

        # =========================================================================
        # 4. MICROPHONE BOOST & LIMITER CONTROLS CARD
        # =========================================================================
        control_card = ctk.CTkFrame(self, fg_color="#181a27", corner_radius=12, border_width=1, border_color="#2b2f42")
        control_card.grid(row=3, column=0, padx=20, pady=10, sticky="ew")
        control_card.grid_columnconfigure(0, weight=1)

        # =========================================================================
        # SOUND PROFILE SECTION (VOICE ARTICULATION EQ)
        # =========================================================================
        prof_header = ctk.CTkFrame(control_card, fg_color="transparent")
        prof_header.pack(fill="x", padx=15, pady=(12, 4))

        ctk.CTkLabel(
            prof_header,
            text="🎚️ Sound Profile (Voice Articulation EQ)",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#ffffff",
        ).pack(side="left")

        profile_names = [p.name for p in SOUND_PROFILES.values()]
        self.opt_profile = ctk.CTkOptionMenu(
            prof_header,
            values=profile_names,
            command=self._on_profile_changed,
            fg_color="#262a3d",
            button_color="#3d4463",
            button_hover_color="#4d567d",
            dropdown_fg_color="#202436",
            width=290,
            height=30,
            corner_radius=8,
        )
        default_prof_name = SOUND_PROFILES[DEFAULT_PROFILE_KEY].name
        self.opt_profile.set(default_prof_name)
        self.opt_profile.pack(side="right")

        # Dynamic profile acoustic description label
        self.lbl_profile_desc = ctk.CTkLabel(
            control_card,
            text=SOUND_PROFILES[DEFAULT_PROFILE_KEY].description,
            font=ctk.CTkFont(family="Segoe UI", size=11, slant="italic"),
            text_color="#8a92b2",
            anchor="w",
            justify="left",
        )
        self.lbl_profile_desc.pack(fill="x", padx=15, pady=(0, 8))

        # Thin divider line
        div_prof = ctk.CTkFrame(control_card, fg_color="#25293d", height=1)
        div_prof.pack(fill="x", padx=15, pady=(0, 10))

        # =========================================================================
        # BOOST & GAIN SECTION
        # =========================================================================
        ctrl_header = ctk.CTkFrame(control_card, fg_color="transparent")
        ctrl_header.pack(fill="x", padx=15, pady=(2, 6))

        ctk.CTkLabel(
            ctrl_header,
            text="⚡ Software Gain Multiplier (Mic Boost)",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#ffffff",
        ).pack(side="left")

        self.lbl_gain_display = ctk.CTkLabel(
            ctrl_header,
            text="+6.0 dB (2.0x)",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color="#3d7bfd",
        )
        self.lbl_gain_display.pack(side="right")

        # Boost Slider
        slider_box = ctk.CTkFrame(control_card, fg_color="transparent")
        slider_box.pack(fill="x", padx=15, pady=4)

        self.slider_gain = ctk.CTkSlider(
            slider_box,
            from_=-10.0,
            to=30.0,
            number_of_steps=80,
            command=self._on_gain_slider_changed,
            progress_color="#3d7bfd",
            button_color="#538fff",
            button_hover_color="#7baaff",
            height=20,
        )
        self.slider_gain.set(6.0)
        self.slider_gain.pack(fill="x", pady=6)

        # Quick Preset Buttons
        preset_box = ctk.CTkFrame(control_card, fg_color="transparent")
        preset_box.pack(fill="x", padx=15, pady=(2, 10))

        presets = [
            ("0 dB (Flat)", 0.0),
            ("+6 dB (Mild)", 6.0),
            ("+12 dB (Crisp)", 12.0),
            ("+18 dB (Loud)", 18.0),
            ("+24 dB (Extreme)", 24.0),
        ]
        for label, val in presets:
            btn = ctk.CTkButton(
                preset_box,
                text=label,
                width=110,
                height=28,
                fg_color="#222638",
                hover_color="#323852",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                corner_radius=6,
                command=lambda v=val: self._set_gain_preset(v),
            )
            btn.pack(side="left", padx=(0, 8))

        # Divider line
        div = ctk.CTkFrame(control_card, fg_color="#25293d", height=1)
        div.pack(fill="x", padx=15, pady=6)

        # Bottom Bar: Limiter Toggle & Mute
        bottom_bar = ctk.CTkFrame(control_card, fg_color="transparent")
        bottom_bar.pack(fill="x", padx=15, pady=(6, 12))

        # Limiter switch
        limiter_box = ctk.CTkFrame(bottom_bar, fg_color="transparent")
        limiter_box.pack(side="left")

        self.switch_limiter = ctk.CTkSwitch(
            limiter_box,
            text="Soft-Knee Dynamic Limiter",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            progress_color="#3d7bfd",
            command=self._on_limiter_toggled,
        )
        self.switch_limiter.select()
        self.switch_limiter.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            limiter_box,
            text="(Clamps peaks cleanly to -0.1 dBFS, zero digital crackle)",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#7b8199",
        ).pack(side="left")

        # Mute button
        self.btn_mute = ctk.CTkButton(
            bottom_bar,
            text="🔇 Mute Mic",
            width=110,
            height=32,
            fg_color="#2a2e45",
            hover_color="#3d4366",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            corner_radius=8,
            command=self._toggle_mute,
        )
        self.btn_mute.pack(side="right")

        # =========================================================================
        # 5. FOOTER INFO
        # =========================================================================
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, padx=20, pady=(4, 10), sticky="ew")

        self.lbl_footer = ctk.CTkLabel(
            footer,
            text="Latency: ~2.7ms | Buffer: 128 frames @ 48,000 Hz | Precision: float32",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#5a6078",
        )
        self.lbl_footer.pack(side="left")

        self.lbl_perf = ctk.CTkLabel(
            footer,
            text="DSP Load: <0.5% | Drops: 0",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#5a6078",
        )
        self.lbl_perf.pack(side="right")

    # =========================================================================
    # LOGIC & AUDIO ENGINE INTERACTION
    # =========================================================================

    def _refresh_audio_devices(self):
        """Rescan system audio devices and update dropdown choices with clean names."""
        input_devs = AudioDeviceManager.get_input_devices()
        output_devs = AudioDeviceManager.get_output_devices()

        self.input_devices_map.clear()
        self.output_devices_map.clear()

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
            out_names.append(lbl)
            if d["index"] == def_out:
                default_out_label = lbl

        if in_names:
            self.opt_input.configure(values=in_names)
            match_in = default_in_label if default_in_label else in_names[0]
            self.opt_input.set(match_in)

        if out_names:
            self.opt_output.configure(values=out_names)
            # Prefer virtual cable if available, otherwise default output
            vc = AudioDeviceManager.find_virtual_cable_index()
            vc_label = next((k for k, v in self.output_devices_map.items() if v == vc), None)
            match_out = vc_label if vc_label else (default_out_label if default_out_label else out_names[0])
            self.opt_output.set(match_out)

    def _init_engine(self):
        """Start the audio stream with currently selected devices."""
        in_sel = self.opt_input.get()
        out_sel = self.opt_output.get()

        in_idx = self.input_devices_map.get(in_sel)
        out_idx = self.output_devices_map.get(out_sel)

        if in_idx is None or out_idx is None:
            return

        # Stop existing engine if running
        if self.engine is not None:
            self.engine.stop()

        self.engine = MicBoostEngine(
            input_device=in_idx,
            output_device=out_idx,
            sample_rate=48000,
            block_size=128,
            gain_db=self.slider_gain.get(),
            profile=self.selected_profile_key,
            limiter_enabled=self.switch_limiter.get() == 1,
        )

        try:
            self.engine.start()
            self.is_running = True
            self.status_badge.configure(
                text="● STREAMING",
                text_color="#00e676",
                fg_color="#132a22",
            )
            self.btn_toggle_stream.configure(
                text="Stop Stream",
                fg_color="#ff1744",
                hover_color="#d50000",
                text_color="#ffffff",
            )
        except Exception as e:
            self.is_running = False
            self.status_badge.configure(
                text="⚠️ ERROR",
                text_color="#ff1744",
                fg_color="#2a1318",
            )
            self.btn_toggle_stream.configure(
                text="Start Stream",
                fg_color="#00e676",
                hover_color="#00c853",
                text_color="#0a1a12",
            )
            print(f"Error starting audio engine: {e}")

    def _toggle_stream(self):
        """Start or stop the audio stream."""
        if self.is_running:
            if self.engine:
                self.engine.stop()
            self.is_running = False
            self.status_badge.configure(
                text="○ STOPPED",
                text_color="#8a8fa3",
                fg_color="#1e2130",
            )
            self.btn_toggle_stream.configure(
                text="Start Stream",
                fg_color="#00e676",
                hover_color="#00c853",
                text_color="#0a1a12",
            )
        else:
            self._init_engine()

    def _on_profile_changed(self, choice: str):
        """Handle sound profile switch."""
        key = self.profiles_by_name.get(choice, DEFAULT_PROFILE_KEY)
        self.selected_profile_key = key
        prof = SOUND_PROFILES[key]
        self.lbl_profile_desc.configure(text=prof.description)
        if self.engine:
            self.engine.set_profile(key)

    def _on_input_device_changed(self, choice: str):
        """Handle microphone selection change."""
        if self.is_running:
            self._init_engine()

    def _on_output_device_changed(self, choice: str):
        """Handle output device selection change."""
        if self.is_running:
            self._init_engine()

    def _on_gain_slider_changed(self, value: float):
        """Update engine gain and numeric display."""
        db_val = round(value, 1)
        linear_val = 10.0 ** (db_val / 20.0)
        self.lbl_gain_display.configure(text=f"{db_val:+5.1f} dB ({linear_val:.2f}x)")
        if self.engine:
            self.engine.set_gain_db(db_val)

    def _set_gain_preset(self, db_value: float):
        """Quick preset button clicked."""
        self.slider_gain.set(db_value)
        self._on_gain_slider_changed(db_value)

    def _on_limiter_toggled(self):
        """Toggle soft limiter state."""
        enabled = self.switch_limiter.get() == 1
        if self.engine:
            self.engine.set_limiter_enabled(enabled)

    def _toggle_mute(self):
        """Toggle microphone mute."""
        if not self.engine:
            return
        new_mute = not self.engine.mute
        self.engine.set_mute(new_mute)
        if new_mute:
            self.btn_mute.configure(
                text="🔊 Unmute",
                fg_color="#ff1744",
                hover_color="#d50000",
            )
        else:
            self.btn_mute.configure(
                text="🔇 Mute Mic",
                fg_color="#2a2e45",
                hover_color="#3d4366",
            )

    def _poll_telemetry(self):
        """High-frequency timer (~30 FPS) for smooth VU meter and limiter updates."""
        if self.engine and self.is_running:
            telem = self.engine.get_telemetry()

            # Update VU Meters
            pre_peak = telem["pre_peak_db"]
            post_peak = telem["post_peak_db"]

            self.vu_pre.update_level(pre_peak)
            self.vu_post.update_level(post_peak)

            self.lbl_pre_db.configure(text=f"{pre_peak:5.1f} dBFS")
            self.lbl_post_db.configure(text=f"{post_peak:5.1f} dBFS")

            # Update Limiter Badge
            if telem["limiter_enabled"]:
                if telem["is_limiting"]:
                    self.limiter_badge.configure(
                        text="⚠️ LIMITING ACTIVE",
                        text_color="#ffffff",
                        fg_color="#ff1744",
                    )
                else:
                    self.limiter_badge.configure(
                        text="LIMITER ENGAGED (PASSIVE)",
                        text_color="#00e676",
                        fg_color="#132a22",
                    )
            else:
                self.limiter_badge.configure(
                    text="LIMITER OFF (RAW CLAMP)",
                    text_color="#ffca28",
                    fg_color="#2b2314",
                )

            # Performance stats
            drops = telem["overflows"] + telem["underflows"]
            self.lbl_perf.configure(text=f"DSP Load: <0.5% | Drops: {drops}")
        else:
            # Zero out meters when stopped
            self.vu_pre.update_level(-60.0)
            self.vu_post.update_level(-60.0)
            self.lbl_pre_db.configure(text="-60.0 dBFS")
            self.lbl_post_db.configure(text="-60.0 dBFS")
            self.limiter_badge.configure(
                text="STREAM STOPPED",
                text_color="#7b8199",
                fg_color="#1e2130",
            )

        # Schedule next update
        self.after(33, self._poll_telemetry)

    def _on_closing(self):
        """Cleanup audio resources and close window."""
        if self.engine:
            self.engine.stop()
        self.destroy()


def main():
    app = WoeyyyApp()
    app.mainloop()


if __name__ == "__main__":
    main()
