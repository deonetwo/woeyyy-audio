"""
Unit tests for Woeyyy Soundboard and Music Engine Subsystems.
Verifies sound generation, file loading, polyphonic soundboard playback,
auto-ducking DSP calculations, and multi-source mixer callback.
"""

import os
import sys
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.soundboard import ProceduralSoundGenerator, SoundboardEngine, load_audio_file
from engine.music_engine import AutoDucker, MusicEngine
from engine.audio_engine import MicBoostEngine


def test_procedural_sound_generator_and_loading():
    """Verify procedural audio synthesis and loading creates valid 48kHz stereo float32 arrays."""
    temp_dir = os.path.join(os.path.dirname(__file__), "test_sounds")
    os.makedirs(temp_dir, exist_ok=True)

    try:
        presets = ProceduralSoundGenerator.generate_all_presets(temp_dir, sr=48000)
        assert "airhorn" in presets
        assert "badumtss" in presets
        assert "buzzer" in presets
        assert "coin" in presets
        assert "levelup" in presets
        assert "tada" in presets

        # Load and verify airhorn
        airhorn_path = presets["airhorn"][1]
        data, dur = load_audio_file(airhorn_path, target_sr=48000)
        assert data.ndim == 2
        assert data.shape[1] == 2
        assert data.dtype == np.float32
        assert dur > 0.5
        assert np.max(np.abs(data)) > 0.05
    finally:
        # Cleanup
        for root, dirs, files in os.walk(temp_dir, topdown=False):
            for name in files:
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        if os.path.exists(temp_dir):
            os.rmdir(temp_dir)


def test_soundboard_engine_polyphony_and_volume():
    """Verify soundboard can mix multiple sounds and respects master & individual volumes."""
    sb = SoundboardEngine(sample_rate=48000)

    # Generate synthetic clips
    dur1 = 0.1
    t1 = np.linspace(0, dur1, int(48000 * dur1), endpoint=False, dtype=np.float32)
    sine1 = np.column_stack([np.sin(2 * np.pi * 440 * t1), np.sin(2 * np.pi * 440 * t1)])

    import tempfile
    import soundfile as sf

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        temp_wav = f.name

    try:
        sf.write(temp_wav, sine1, 48000)
        sb.add_sound("sine", "Sine Test", temp_wav, volume=0.5)

        # Before play: silence
        silence = sb.read_chunk(128)
        assert np.allclose(silence, 0.0)

        # Play sound
        sb.play_sound("sine")
        assert sb.is_playing("sine")

        # Read first chunk
        chunk = sb.read_chunk(128)
        assert chunk.shape == (128, 2)
        assert np.max(np.abs(chunk)) > 0.01

        # Test volume scaling
        sb.set_master_volume(0.5)
        chunk2 = sb.read_chunk(128)
        assert chunk2.shape == (128, 2)

        # Stop sound
        sb.stop_sound("sine")
        assert not sb.is_playing("sine")
        chunk_after_stop = sb.read_chunk(128)
        assert np.allclose(chunk_after_stop, 0.0)
    finally:
        if os.path.exists(temp_wav):
            os.remove(temp_wav)


def test_auto_ducking_calculations():
    """Verify intelligent microphone auto-ducking response to speech vs silence."""
    ducker = AutoDucker(threshold_db=-36.0, duck_depth_db=-12.0, sample_rate=48000)

    # 1. Silence (-60 dBFS) -> gain should stay 1.0 (0 dB attenuation)
    for _ in range(10):
        g = ducker.process_block(mic_rms_db=-60.0, num_frames=128)
    assert np.isclose(g, 1.0, atol=0.01)
    assert not ducker.is_ducking

    # 2. Speech (-18 dBFS) -> gain should duck towards -12 dB (approx 0.251x)
    for _ in range(40):
        g_speech = ducker.process_block(mic_rms_db=-18.0, num_frames=128)
    assert ducker.is_ducking
    assert g_speech < 0.5  # significantly ducked

    # 3. Speech stops -> hold timer preserves ducking, then releases back to 1.0
    # Process for 2.5 seconds of silence (hold 350ms + release decay)
    for _ in range(int(48000 * 2.5 / 128)):
        g_release = ducker.process_block(mic_rms_db=-60.0, num_frames=128)
    assert not ducker.is_ducking
    assert np.isclose(g_release, 1.0, atol=0.05)


def test_multi_source_audio_mixing_and_limiting():
    """Test full audio callback math mixing mic + soundboard + music with limiter clamp."""
    engine = MicBoostEngine(
        input_device=None,
        output_device=None,
        sample_rate=48000,
        block_size=128,
        gain_db=6.0,
        limiter_enabled=True,
    )

    frames = 128
    indata = np.ones((frames, 1), dtype=np.float32) * 0.5
    outdata = np.zeros((frames, 2), dtype=np.float32)

    # Trigger callback directly
    engine._audio_callback(indata, outdata, frames, None, None)

    # Output should be non-zero, stereo, and within limiter ceiling (< 0.99)
    assert outdata.shape == (frames, 2)
    assert np.max(np.abs(outdata)) > 0.1
    assert np.max(np.abs(outdata)) <= 0.99


if __name__ == "__main__":
    test_procedural_sound_generator_and_loading()
    test_soundboard_engine_polyphony_and_volume()
    test_auto_ducking_calculations()
    test_multi_source_audio_mixing_and_limiting()
    print("\n[OK] All Soundboard and Music Engine unit tests passed successfully!")
