# Woeyyy - Real-Time Soundboard, YouTube Music Player & Microphone Enhancer 🎙️🔊🎵

Woeyyy is a high-performance, low-latency audio engine, polyphonic soundboard, and streaming center designed for Discord, VoIP, and gaming. It blends live microphone input, soundboard audio clips, and YouTube Music (from web browser or direct streaming) into a Virtual Audio Cable with real-time software gain boost and dynamic soft-knee clipping protection.

---

## 🏗️ Multi-Source Audio Architecture

```
[ 1. Real Mic Input ] ──────> [ Articulation EQ ] ──> [ Digital Mic Booster ] ─┐
                                                                                │
[ 2. Soundboard Clips ] ────> [ 48kHz Resampler ] ──> [ Soundboard Volume ] ────┼──> [ Master Soft-Limiter ] ──> [ Virtual Cable ] ──> [ Discord / Game ]
                                                                                │         (-0.1 dBFS)             (CABLE Input)
[ 3. YouTube Music Engine ] ─> [ Resampler Buffer ] ─> [ Music Vol & Ducking ] ─┘
     ├── Mode A: Web Browser WASAPI Loopback (Chrome / Edge / YouTube Music Web)
     └── Mode B: Built-in YouTube Music Stream Player (yt-dlp & PyAV)

[ Soundboard & Stream Music ] ──────────────────────────────────────────────────> [ Headphone Monitor ] (Self-Listen)
```

---

## ⚡ Key Features

- **Polyphonic Soundboard:**
  - Zero-latency in-memory float32 cache at 48 kHz.
  - Multi-format support: `.mp3`, `.wav`, `.ogg`, `.flac`, `.m4a`, `.aac`.
  - Built-in procedural sound generator (Airhorn MLG, Ba-Dum-Tss, Buzzer, 8-Bit Coin, Level Up, Tada, Siren, Laser) ready to play instantly out-of-the-box.
  - Global hotkeys (`1`–`8`, F-keys, Numpad) via `pynput` working even when tabbed into games.
  - Master volume slider and Panic Stop All button.
- **YouTube Music & Web Browser Stream (into Mic):**
  - **Mode A (Web Browser Loopback):** Captures YouTube Music audio directly from your browser (Chrome/Edge/Firefox) via Windows WASAPI Loopback and routes it into your microphone.
  - **Mode B (Built-in Stream Player):** Paste any YouTube or YouTube Music link (`music.youtube.com/watch?v=...`) to stream directly in the app without browser overhead.
  - **Intelligent Auto-Ducking:** Automatically lowers music volume (e.g. by -12 dB) whenever you speak into the microphone, then smoothly restores it when you stop talking.
- **Microphone Articulation & Digital Boost:**
  - Real-time software amplification up to $+36\text{ dB}$ ($63\text{x}$) with click-free parameter smoothing.
  - 4 Vocal EQ Profiles: *Clear Voice & Articulation*, *Crisp Comms*, *Broadcast Warmth*, and *Flat Bypass*.
- **Master Soft-Knee Saturation & Limiter:**
  - Absolute peak clamp at $-0.1\text{ dBFS}$ prevents digital clipping regardless of how loud the music, soundboard, or voice gets.
- **Headphone Monitor (Self-Listen):**
  - Listen to soundboard audio and music in your headset with zero feedback echo.
- **Dual High-FPS VU Meters:**
  - Real-time telemetry for raw microphone input and master combined output.

---

## 🚀 Quick Start

### 1. Requirements & Setup
Ensure Python 3.10+ is installed:
```powershell
pip install -r requirements.txt
```

*(Ensure [VB-Audio Virtual Cable](https://vb-audio.com/Cable/) is installed to route into Discord/Games).*

### 2. Launch the Desktop GUI
```powershell
python gui.py
# or
python main.py
```

### 3. Audio Routing for Discord / Games
1. In **Woeyyy**:
   - **Microphone Input:** Choose your physical microphone (e.g., *SteelSeries Arctis 1 Wireless*).
   - **Output Device:** Choose `CABLE Input (VB-Audio Virtual Cable)`.
   - **Headphone Monitor:** Choose your physical headphones (e.g., *Speakers (SteelSeries Arctis 1)*).
2. In **Discord / Game Settings**:
   - **Input Device (Microphone):** Select `CABLE Output (VB-Audio Virtual Cable)`.
   - **Output Device (Headphones):** Select your normal headphones.

---

## 🌐 Cara Menggunakan YouTube Music ke dalam Mic

### Cara 1: Web Browser Loopback (YouTube Music Web)
1. Buka [music.youtube.com](https://music.youtube.com) di Google Chrome, Microsoft Edge, atau browser favorit Anda dan putar lagu.
2. Di aplikasi Woeyyy, buka tab **🎵 YouTube Music & Web**.
3. Aktifkan sakelar **Capture Browser Audio (ON/OFF)**.
4. Musik akan otomatis mengalir ke microphone Discord Anda! Saat Anda berbicara di mic, fitur **Auto-Ducking** akan otomatis mengecilkan volume lagu agar suara Anda tetap terdengar jelas.

### Cara 2: Built-in YouTube Music Stream Player
1. Salin link lagu dari YouTube atau YouTube Music (contoh: `https://music.youtube.com/watch?v=...`).
2. Tempelkan link ke kotak input pada tab **🎵 YouTube Music & Web**.
3. Klik **Stream Track**.

---

## 🧪 Testing & Verification

To run the automated unit tests:
```powershell
# Run DSP and voice profile tests
python tests/test_dsp.py

# Run Soundboard and Music Engine tests
python tests/test_soundboard_and_music.py
```
