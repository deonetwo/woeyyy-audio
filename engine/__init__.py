"""
Woeyyy - Real-Time Soundboard & Microphone Enhancer
Core Engine Package
"""

from .audio_engine import AudioDeviceManager, MicBoostEngine
from .discord_bot import DiscordVoiceBot
from .dsp import (
    BiquadFilter,
    ParametricEQChain,
    SoftLimiter,
    calculate_levels,
    db_to_linear,
    linear_to_db,
)
from .profiles import DEFAULT_PROFILE_KEY, SOUND_PROFILES, SoundProfile

__all__ = [
    "MicBoostEngine",
    "AudioDeviceManager",
    "DiscordVoiceBot",
    "SoftLimiter",
    "BiquadFilter",
    "ParametricEQChain",
    "SoundProfile",
    "SOUND_PROFILES",
    "DEFAULT_PROFILE_KEY",
    "calculate_levels",
    "db_to_linear",
    "linear_to_db",
]
