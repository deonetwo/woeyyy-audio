# Woeyyy - Real-Time Soundboard & Microphone Enhancer 🎙️🔊

Woeyyy is a high-performance, low-latency audio engine and soundboard designed for Discord, VoIP, and gaming. It blends live microphone input with soundboard audio into a Virtual Audio Cable with real-time software gain boost and dynamic soft-knee clipping protection.

---

## 🏗️ Architecture

```
[ Real Mic Input ] ──> [ Mic Boost & Limiter Engine ] ──┐
                                                         ├──> [ Python Blend Engine ] ──> [ Virtual Cable ] ──> [ Discord / VoIP / Game ]
                       [ Soundboard Audio Files ] ───────┘
```

---

## ⚡ Priority 1 Features (Current Release)

- **Vectorized Digital Gain Multiplier:** Real-time software amplification from $-20\text{ dB}$ to $+40\text{ dB}$ with sample-accurate linear parameter smoothing (eliminates clicks/pops when sliders move).
- **Soft-Knee Saturation & Limiter:**
  - $100\%$ bit-exact transparency below threshold ($-1.0\text{ dBFS}$).
  - $C^1$-continuous hyperbolic tangent ($\tanh$) soft saturation above threshold.
  - Absolute peak ceiling clamp ($-0.1\text{ dBFS}$ / $0.988$) preventing harsh digital distortion.
- **Ultra-Low Latency:** Optimized for small buffer block sizes ($128$ to $256$ frames at $48\text{ kHz}$ / $44.1\text{ kHz}$), running DSP calculations in $\approx 0.012\text{ ms}$ ($<0.5\%$ of the $2.6\text{ ms}$ buffer budget).
- **Live Terminal VU Meter:** Real-time visual telemetry for pre-boost mic level, gain value, limiter engagement status, and final output level.

---

## 🚀 Quick Start

### 1. Requirements & Setup
Ensure Python 3.10+ is installed:
```powershell
pip install -r requirements.txt
```

*(Optional for routing into Discord/Games without hearing yourself: install [VB-Audio Virtual Cable](https://vb-audio.com/Cable/))*

### 2. Launch the Desktop GUI
```powershell
python gui.py
# or
python main.py
```

### 3. Launch the Terminal/CLI Harness (Optional)
If you prefer running inside a headless shell or terminal:
```powershell
python run_mic_boost.py
# or
python main.py --cli
```

---

## 🎛️ Controls & Features

### Sound Profiles & Voice Articulation EQ
- **🌟 Clear Voice & Articulation (Default):** Specifically engineered to eliminate muddy bass boominess, cut boxy microphone resonance, and bring speech consonants (T, S, K, P) forward for crystal-clear communication.
  - **$100\text{ Hz}$ High-Pass Filter:** Cuts desk thumps, mechanical rumble, and muddy bass proximity effect ($-15.7\text{ dB}$ sub-bass cut).
  - **$320\text{ Hz}$ Mud Scoop ($-4.0\text{ dB}$):** Removes hollow, muffled "cardboard box" nasal sound.
  - **$3.2\text{ kHz}$ Articulation Boost ($+4.5\text{ dB}$):** Sharpens vocal clarity, presence, and diction.
  - **$8.5\text{ kHz}$ Air Shelf ($+2.5\text{ dB}$):** Adds a clean, open studio sheen.
- **🎮 Crisp Comms & Gaming:** Aggressive low-cut ($150\text{ Hz}$) and heavy speech core boost ($+6.0\text{ dB}$) to penetrate through loud in-game explosions and gunfire.
- **🎙️ Broadcast Warmth:** Rich, intimate radio tone with warm low-mid body.
- **⚪ Flat (Bypass):** Pure, uncolored microphone signal.

### Desktop GUI
- **Sound Profile Selector:** One-click dropdown to instantly switch voice EQ curves with live acoustic descriptions.
- **Microphone & Output Selectors:** Clean WASAPI dropdowns listing physical mics and Virtual Audio Cables without duplicate clutter.
- **Microphone Boost Slider:** Smooth gain slider from $-10\text{ dB}$ to $+30\text{ dB}$ ($0.3\text{x}$ to $31.6\text{x}$ amplification) with quick presets (`Flat`, `+6dB`, `+12dB`, `+18dB`, `+24dB`).
- **Live Dual VU Meters:** Animated high-framerate level meters with green/yellow/red audio thresholds and decaying peak-hold indicators for both raw mic and boosted output.
- **Dynamic Soft-Limiter Switch:** Soft-saturation protection prevents harsh digital clipping when screaming or speaking loudly.
- **Mute Toggle:** Instant click-free microphone muting.

### Terminal Mode Hotkeys
| Key | Action |
|---|---|
| `+` / `=` | Increase Gain by $+1\text{ dB}$ |
| `-` / `_` | Decrease Gain by $-1\text{ dB}$ |
| `]` | Increase Gain by $+5\text{ dB}$ |
| `[` | Decrease Gain by $-5\text{ dB}$ |
| `P` | Cycle Sound Profile (Clear Voice, Comms, Warm, Flat) |
| `L` | Toggle Soft-Limiter ON / OFF |
| `M` | Toggle Mute ON / OFF |
| `Q` / `Ctrl+C` | Exit Cleanly |

---

## 🧪 Testing & Verification
To run the automated DSP unit tests and latency benchmark:
```powershell
python tests/test_dsp.py
```

---

## 🗺️ Roadmap
- [x] **Priority 1: Real-time Microphone Boost & Limiter Engine**
- [ ] **Priority 2: Soundboard Audio Blend Engine** (Seamlessly mixing `.wav` / `.mp3` audio files into live stream)
- [ ] **Priority 3: Global Hotkeys** (Registering system-wide hotkeys while gaming using `pynput`)
- [ ] **Priority 4: Modern Desktop GUI** (Sleek dark-mode interface with sliders, VU visualizer, and soundboard pads)
