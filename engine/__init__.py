"""
Woeyyy - Real-Time Soundboard & Microphone Enhancer
Core Engine Package
"""

# Discord bot engine (headless cloud compatible)
try:
    from .discord_bot import DiscordVoiceBot
except ImportError:
    DiscordVoiceBot = None

# Audio DSP & device manager (requires numpy, scipy, sounddevice)
try:
    from .audio_engine import AudioDeviceManager, MicBoostEngine
except ImportError:
    AudioDeviceManager, MicBoostEngine = None, None

try:
    from .dsp import (
        BiquadFilter,
        ParametricEQChain,
        SoftLimiter,
        calculate_levels,
        db_to_linear,
        linear_to_db,
    )
except ImportError:
    pass

try:
    from .profiles import DEFAULT_PROFILE_KEY, SOUND_PROFILES, SoundProfile
except ImportError:
    pass

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
