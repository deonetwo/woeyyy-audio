"""
Woeyyy Core Audio Engine
Real-time low-latency stream management, device enumeration, gain boosting, and limiter routing.
"""

import sys
import threading
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import sounddevice as sd

from .dsp import ParametricEQChain, SoftLimiter, calculate_levels, db_to_linear, linear_to_db
from .profiles import DEFAULT_PROFILE_KEY, SOUND_PROFILES, SoundProfile


class AudioDeviceManager:
    """Manages audio device querying, filtering, and virtual cable discovery."""

    @staticmethod
    def get_wasapi_hostapi_index() -> Optional[int]:
        """Find host API index for Windows WASAPI (lowest latency, clean names)."""
        try:
            for idx, api in enumerate(sd.query_hostapis()):
                if "wasapi" in api.get("name", "").lower():
                    return idx
        except Exception:
            pass
        return None

    @staticmethod
    def get_input_devices(wasapi_only: bool = True) -> List[Dict]:
        """
        Return list of clean audio input devices.
        On Windows, filters to WASAPI to eliminate duplicates from legacy MME/DirectSound.
        """
        devices = sd.query_devices()
        wasapi_idx = AudioDeviceManager.get_wasapi_hostapi_index() if wasapi_only else None

        input_devs = []
        for idx, dev in enumerate(devices):
            if dev.get("max_input_channels", 0) <= 0:
                continue
            # If WASAPI is active, keep only WASAPI devices
            if wasapi_idx is not None and dev.get("hostapi") != wasapi_idx:
                continue
            # Ignore legacy virtual wrappers / mappers
            name = dev.get("name", "")
            if any(ign in name.lower() for ign in ["sound mapper", "primary sound capture"]):
                continue

            d = dict(dev)
            d["index"] = idx
            input_devs.append(d)

        # Fallback if wasapi returned no devices
        if not input_devs and wasapi_only:
            return AudioDeviceManager.get_input_devices(wasapi_only=False)
        return input_devs

    @staticmethod
    def get_output_devices(wasapi_only: bool = True) -> List[Dict]:
        """
        Return list of clean audio output devices.
        On Windows, filters to WASAPI to eliminate duplicates from legacy MME/DirectSound.
        """
        devices = sd.query_devices()
        wasapi_idx = AudioDeviceManager.get_wasapi_hostapi_index() if wasapi_only else None

        output_devs = []
        for idx, dev in enumerate(devices):
            if dev.get("max_output_channels", 0) <= 0:
                continue
            if wasapi_idx is not None and dev.get("hostapi") != wasapi_idx:
                continue
            name = dev.get("name", "")
            if any(ign in name.lower() for ign in ["sound mapper", "primary sound driver"]):
                continue

            d = dict(dev)
            d["index"] = idx
            output_devs.append(d)

        if not output_devs and wasapi_only:
            return AudioDeviceManager.get_output_devices(wasapi_only=False)
        return output_devs

    @staticmethod
    def get_default_input_index() -> Optional[int]:
        """Return device index for system default input (preferring WASAPI)."""
        try:
            wasapi_idx = AudioDeviceManager.get_wasapi_hostapi_index()
            if wasapi_idx is not None:
                api_info = sd.query_hostapis(wasapi_idx)
                def_in = api_info.get("default_input_device")
                if def_in is not None and def_in != -1:
                    return def_in

            default_in = sd.default.device[0]
            if default_in != -1:
                return default_in
            devs = AudioDeviceManager.get_input_devices()
            return devs[0]["index"] if devs else None
        except Exception:
            return None

    @staticmethod
    def get_default_output_index() -> Optional[int]:
        """Return device index for system default output (preferring WASAPI)."""
        try:
            wasapi_idx = AudioDeviceManager.get_wasapi_hostapi_index()
            if wasapi_idx is not None:
                api_info = sd.query_hostapis(wasapi_idx)
                def_out = api_info.get("default_output_device")
                if def_out is not None and def_out != -1:
                    return def_out

            default_out = sd.default.device[1]
            if default_out != -1:
                return default_out
            devs = AudioDeviceManager.get_output_devices()
            return devs[0]["index"] if devs else None
        except Exception:
            return None

    @staticmethod
    def find_virtual_cable_index() -> Optional[int]:
        """
        Search for popular virtual audio cable input devices (e.g., VB-Cable, VoiceMeeter).
        Returns device index if found, else None.
        """
        keywords = ["cable input", "vb-audio", "virtual cable", "voicemeeter"]
        for dev in AudioDeviceManager.get_output_devices():
            name_lower = dev.get("name", "").lower()
            if any(kw in name_lower for kw in keywords):
                return dev["index"]
        return None


class MicBoostEngine:
    """
    Real-time low-latency microphone boost and processing engine.
    
    Streams live audio from real microphone -> applies digital gain ->
    soft-knee limiter & dynamic protection -> writes to virtual cable output.
    """

    def __init__(
        self,
        input_device: Optional[int] = None,
        output_device: Optional[int] = None,
        sample_rate: int = 48000,
        block_size: int = 128,
        in_channels: int = 1,
        out_channels: int = 2,
        gain_db: float = 0.0,
        profile: str = DEFAULT_PROFILE_KEY,
        limiter_enabled: bool = True,
        limiter_threshold_db: float = -1.0,
        limiter_ceiling_db: float = -0.1,
    ):
        self.sample_rate = sample_rate
        self.block_size = block_size
        self.in_channels = in_channels
        self.out_channels = out_channels

        # Thread synchronization lock
        self._lock = threading.Lock()

        # Device selection
        self.input_device = (
            input_device if input_device is not None else AudioDeviceManager.get_default_input_index()
        )
        self.output_device = (
            output_device if output_device is not None else AudioDeviceManager.get_default_output_index()
        )

        # Gain settings
        self._target_gain_db = gain_db
        self._target_gain_linear = db_to_linear(gain_db)
        self._current_gain_linear = self._target_gain_linear
        self.mute = False

        # Sound Profile & Equalizer Chain
        self._profile_key = profile
        self.eq_chain = ParametricEQChain(sample_rate=self.sample_rate, channels=self.in_channels)
        self.set_profile(profile)

        # Limiter processor
        self.limiter_enabled = limiter_enabled
        self.limiter = SoftLimiter(
            threshold_db=limiter_threshold_db,
            ceiling_db=limiter_ceiling_db,
            sample_rate=sample_rate,
            mode="soft_knee",
        )

        # Telemetry / VU Meter metrics (lock-free thread-safe updates)
        self.pre_peak_db = -96.0
        self.pre_rms_db = -96.0
        self.post_peak_db = -96.0
        self.post_rms_db = -96.0
        self.is_limiting = False
        self.buffer_underflow_count = 0
        self.buffer_overflow_count = 0

        # Stream instance & state
        self._stream: Optional[sd.Stream] = None
        self._running = False

    @property
    def is_running(self) -> bool:
        """Whether the audio stream is currently active."""
        return self._running and self._stream is not None and self._stream.active

    @property
    def gain_db(self) -> float:
        """Current target gain in decibels."""
        return self._target_gain_db

    @property
    def current_profile(self) -> str:
        """Currently active sound profile key."""
        return self._profile_key

    def set_profile(self, profile_key: str):
        """Switch active sound profile (updates EQ filter bands seamlessly)."""
        with self._lock:
            if profile_key not in SOUND_PROFILES:
                profile_key = DEFAULT_PROFILE_KEY
            self._profile_key = profile_key
            prof = SOUND_PROFILES[profile_key]
            self.eq_chain.configure_bands(prof.bands)

    def set_gain_db(self, gain_db: float):
        """Set digital boost gain in decibels (smoothly interpolated across buffer)."""
        with self._lock:
            self._target_gain_db = float(gain_db)
            self._target_gain_linear = db_to_linear(gain_db)

    def set_limiter_enabled(self, enabled: bool):
        """Enable or disable the soft-knee limiter."""
        with self._lock:
            self.limiter_enabled = enabled
            self.limiter.enabled = enabled

    def set_mute(self, mute: bool):
        """Mute or unmute the microphone stream."""
        with self._lock:
            self.mute = mute

    def get_telemetry(self) -> Dict[str, Union[float, bool, int, str]]:
        """Retrieve latest snapshot of VU levels, limiter state, profile, and stream stats."""
        return {
            "pre_peak_db": self.pre_peak_db,
            "pre_rms_db": self.pre_rms_db,
            "post_peak_db": self.post_peak_db,
            "post_rms_db": self.post_rms_db,
            "gain_db": self._target_gain_db,
            "profile": self._profile_key,
            "is_limiting": self.is_limiting,
            "is_muted": self.mute,
            "limiter_enabled": self.limiter_enabled,
            "overflows": self.buffer_overflow_count,
            "underflows": self.buffer_underflow_count,
        }

    def _audio_callback(self, indata: np.ndarray, outdata: np.ndarray, frames: int, time_info, status):
        """
        High-priority real-time audio processing callback.
        Kept lean and 100% vectorized for sub-millisecond execution.
        """
        if status:
            if status.input_overflow:
                self.buffer_overflow_count += 1
            if status.output_underflow:
                self.buffer_underflow_count += 1

        # 1. Sound Profile Equalization (Voice Articulation & Anti-Bass filtering)
        equalized = self.eq_chain.process(indata)

        # 2. Pre-gain metering
        pre_peak, pre_rms = calculate_levels(equalized)
        self.pre_peak_db = pre_peak
        self.pre_rms_db = pre_rms

        # 3. Check mute
        if self.mute:
            outdata.fill(0.0)
            self.post_peak_db = -96.0
            self.post_rms_db = -96.0
            self.is_limiting = False
            return

        # 4. Vectorized Gain Application with click-free parameter smoothing
        target_g = self._target_gain_linear
        curr_g = self._current_gain_linear

        if abs(curr_g - target_g) > 1e-4:
            # Linear interpolation across buffer frames to eliminate zipper noise
            ramp = np.linspace(curr_g, target_g, frames, dtype=np.float32)
            if equalized.ndim > 1:
                ramp = ramp[:, np.newaxis]
            boosted = equalized * ramp
            self._current_gain_linear = target_g
        else:
            boosted = equalized * target_g

        # 4. Limiter / Soft-Clipping Protection
        if self.limiter_enabled:
            # Fast check if limiting occurs
            boosted_peak = float(np.max(np.abs(boosted)))
            self.is_limiting = boosted_peak > self.limiter.threshold
            processed = self.limiter.process(boosted)
        else:
            # Safety hard clip when limiter is disabled
            self.is_limiting = False
            processed = np.clip(boosted, -1.0, 1.0)

        # 5. Channel mapping (handle mono mic to stereo output cleanly)
        if self.in_channels == 1 and self.out_channels == 2:
            outdata[:, 0] = processed[:, 0]
            outdata[:, 1] = processed[:, 0]
        elif self.in_channels == 2 and self.out_channels == 1:
            outdata[:, 0] = np.mean(processed, axis=1)
        else:
            min_ch = min(self.in_channels, self.out_channels)
            outdata[:, :min_ch] = processed[:, :min_ch]
            if self.out_channels > min_ch:
                outdata[:, min_ch:] = 0.0

        # 6. Post-gain metering
        post_peak, post_rms = calculate_levels(outdata)
        self.post_peak_db = post_peak
        self.post_rms_db = post_rms

    def start(self):
        """Start the real-time audio stream."""
        if self._running:
            return

        # Query devices to verify channel capabilities
        try:
            in_info = sd.query_devices(self.input_device, "input")
            max_in = in_info.get("max_input_channels", 1)
            self.in_channels = min(self.in_channels, max_in)
        except Exception:
            pass

        try:
            out_info = sd.query_devices(self.output_device, "output")
            max_out = out_info.get("max_output_channels", 2)
            self.out_channels = min(self.out_channels, max_out)
        except Exception:
            pass

        self.limiter.sample_rate = self.sample_rate
        self.limiter.reset()

        self._stream = sd.Stream(
            device=(self.input_device, self.output_device),
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            dtype="float32",
            latency="low",
            channels=(self.in_channels, self.out_channels),
            callback=self._audio_callback,
        )
        self._stream.start()
        self._running = True

    def stop(self):
        """Stop and close the real-time audio stream."""
        self._running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            finally:
                self._stream = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
