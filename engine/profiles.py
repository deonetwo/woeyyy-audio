"""
Woeyyy Sound Profiles
Pre-tuned equalizer profiles for voice clarity, anti-bass boominess, and gaming comms.
"""

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class EQBand:
    """Represents a single parametric equalizer band."""
    filter_type: str  # 'highpass', 'peaking', 'highshelf', 'lowshelf'
    freq: float       # Center / Cutoff frequency in Hz
    gain_db: float    # Gain in decibels (for peaking, shelves)
    q: float = 0.707  # Quality factor (bandwidth)


@dataclass
class SoundProfile:
    """Defines an audio enhancement profile with display metadata and EQ bands."""
    key: str
    name: str
    description: str
    bands: List[EQBand] = field(default_factory=list)


# Built-in sound profiles
SOUND_PROFILES: Dict[str, SoundProfile] = {
    "clear_voice": SoundProfile(
        key="clear_voice",
        name="🌟 Clear Voice & Articulation (Default)",
        description="Cuts muddy bass boominess (<100Hz), scoops boxy mids (320Hz), and boosts consonant clarity (3.2kHz).",
        bands=[
            # 1. High-Pass: eliminates desk thumps, AC rumble, and muddy proximity effect
            EQBand(filter_type="highpass", freq=100.0, gain_db=0.0, q=0.707),
            # 2. Mud Scoop: removes muffled 'cardboard box' resonance
            EQBand(filter_type="peaking", freq=320.0, gain_db=-4.0, q=1.2),
            # 3. Speech Articulation & Consonant Presence (T, S, K, P clarity)
            EQBand(filter_type="peaking", freq=3200.0, gain_db=4.5, q=1.0),
            # 4. Air & Sheen: smooth studio broadcast finish
            EQBand(filter_type="highshelf", freq=8500.0, gain_db=2.5, q=0.707),
        ],
    ),
    "crisp_comms": SoundProfile(
        key="crisp_comms",
        name="🎮 Crisp Comms & Gaming",
        description="Aggressive anti-rumble with boosted vocal presence to cut through loud game audio and explosions.",
        bands=[
            EQBand(filter_type="highpass", freq=150.0, gain_db=0.0, q=0.707),
            EQBand(filter_type="peaking", freq=400.0, gain_db=-5.0, q=1.4),
            EQBand(filter_type="peaking", freq=2800.0, gain_db=6.0, q=1.1),
            EQBand(filter_type="highshelf", freq=7500.0, gain_db=2.0, q=0.707),
        ],
    ),
    "broadcast_warm": SoundProfile(
        key="broadcast_warm",
        name="🎙️ Broadcast Warmth (Podcast)",
        description="Subtle low-end body with balanced vocal presence for a rich, intimate radio tone.",
        bands=[
            EQBand(filter_type="highpass", freq=70.0, gain_db=0.0, q=0.707),
            EQBand(filter_type="lowshelf", freq=160.0, gain_db=2.0, q=0.707),
            EQBand(filter_type="peaking", freq=3500.0, gain_db=2.5, q=1.0),
            EQBand(filter_type="highshelf", freq=9000.0, gain_db=2.0, q=0.707),
        ],
    ),
    "flat": SoundProfile(
        key="flat",
        name="⚪ Flat (Bypass / Direct Mic)",
        description="Raw microphone audio without any equalization coloring.",
        bands=[],
    ),
}

DEFAULT_PROFILE_KEY = "clear_voice"
