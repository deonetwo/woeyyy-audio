# Woeyyy Audio Suite 🎙️⚡🤖

**Woeyyy** is a high-performance, low-latency audio utility and Discord Hi-Fi streaming engine built with Python. It provides studio-grade microphone digital amplification, soft-knee clipping protection, polyphonic soundboards, and an embedded 48kHz Stereo Opus Discord Voice Bot with slash command integration.

---

## 🎯 Dual Edition Architecture

Woeyyy is architected to fit two distinct workflows without compromise:

| Feature / Edition | **Woeyyy Lite** (Recommended) | **Woeyyy Original** (Full Suite) | **Headless Bot** (Cloud / CLI) |
|---|:---:|:---:|:---:|
| **Target User** | Everyday gaming & Discord voice comms | Audio enthusiast & Soundboard studio | 24/7 Cloud server (AWS / VPS) |
| **Interface** | Minimalist Dark Slate (`520x760px`) | Full Multitab Studio (`920x840px`) | Headless Terminal / Daemon |
| **Mic Booster** | ✅ 0 to +36 dB (~63x amplification) | ✅ 0 to +36 dB with Vocal EQ | ❌ None (Audio Bot only) |
| **Soft-Knee Limiter** | ✅ Peak clamp at -0.1 dBFS | ✅ Peak clamp at -0.1 dBFS | ❌ None |
| **Discord Music Bot** | ✅ 48kHz Stereo Opus direct streaming | ❌ Unattached | ✅ Full background daemon |
| **Favorite Music** | ✅ 1-click star bookmarking & queue | ❌ None | ❌ None |
| **Soundboard** | ❌ None (Clean & compact) | ✅ 8-slot polyphonic + Hotkeys | ✅ CLI trigger (`sb <name>`) |
| **Session Persistence**| ✅ Auto-saves devices, gain & favs | ❌ Session-only | ✅ Token config |
| **One-Click Launcher** | `run_lite.bat` | `run.bat` | `run_bot.bat` |

---

## ✨ Features Breakdown

### 1. 🎤 Real-Time Microphone Booster (Lite & Original)
- **High-Dynamic Gain:** Clean, click-free software amplification from `0.0 dB` up to `+36.0 dB` (~63x linear amplification).
- **Master Soft-Knee Limiter:** Dynamic saturation curve with an absolute ceiling at `-0.1 dBFS` prevents digital clipping and ear-piercing distortion.
- **Hardware Agnostic:** Automatically enumerates and binds to any input and output audio device (e.g. physical microphones, USB headsets, or Virtual Audio Cables).
- **Session Persistence (Lite):** Automatically remembers your selected input device, output device, gain setting, and toggle states across restarts.

### 2. 🤖 Discord Hi-Fi Voice Bot (Lite & Headless)
- **Studio 48kHz Opus Streaming:** Direct in-memory UDP streaming straight to Discord voice channels at native 48,000 Hz stereo Opus quality.
- **Zero Echo / Noise Suppression Cutoff:** Completely bypasses Discord Krisp and noise-cancellation filtering for crystal-clear music playback.
- **Universal Streaming Support:** Plays directly from YouTube, YouTube Music (`music.youtube.com`), and direct audio streams via `yt-dlp` without local file saving.
- **Discord Slash Commands (/):** Control the bot directly from any Discord text channel:
  - `/play <title or url>` — Play or enqueue music with automatic track resolution.
  - `/skip` — Skip the active song and seamlessly transition to the next queued track.
  - `/queue` — View the upcoming song queue and requesters.
  - `/join` — Summon the bot to your current voice channel.
  - `/leave` — Disconnect the bot from voice.
  - `/stop` — Stop audio playback.

### 3. ⭐ Favorite Music System (Woeyyy Lite)
- **1-Click Star Bookmarking:** Click the ⭐ Star button to bookmark the currently streaming track or any typed song title/URL.
- **Automatic Metadata Resolution:** Resolves real track titles and canonical URLs in the background before saving (no ugly raw URLs in your list).
- **Quick Queue (`+ Queue`):** Enqueues your favorite track into the bot's queue with one click without interrupting or cutting off the song currently playing.
- **Persistent Storage:** Stored in `.lite_config.json` so your favorite songs are always ready when you launch the app.

### 4. 🛡️ Kernel-Level Security & Single-Instance Lock
- **Windows Named Mutex:** Uses `Local\Woeyyy_Audio_Suite_SingleInstance_Mutex` to ensure strictly one active audio session runs at a time, preventing PortAudio hardware conflicts and duplicate Discord Gateway sessions.
- **Automatic Window Recovery:** Launching a second instance automatically brings the already running application window to the foreground.
- **SSRF & Dangerous Protocol Protection:** Automatically blocks streaming attempts targeting loopback addresses (`127.0.0.1`, `localhost`), private subnets (`10.0.0.0/8`, `192.168.0.0/16`), cloud metadata endpoints (`169.254.169.254`), and unsafe protocols (`file://`, `pipe:`, `concat:`).
- **Windows ACL Token Hardening:** Discord token storage permissions are locked via Windows `icacls`, restricting read and write access exclusively to the active user account.

---

## 🚀 Quick Start

### 1. Prerequisites
- **Operating System:** Windows 10/11 (or Ubuntu 22.04+ for Headless Bot).
- **Python:** Python 3.10 to 3.14.

### 2. Installation
Clone the repository and install dependencies:

```powershell
git clone https://github.com/dewanto-ar/woeyyy-audio.git
cd woeyyy-audio

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Running Woeyyy

Choose the launcher that matches your desired mode:

- **Woeyyy Lite (Compact & Modern):**
  ```powershell
  .\run_lite.bat
  # or
  python main.py --lite
  ```

- **Woeyyy Original (Full Soundboard Suite):**
  ```powershell
  .\run.bat
  # or
  python main.py
  ```

- **Headless Discord Bot (Terminal Mode):**
  ```powershell
  .\run_bot.bat
  # or
  python main.py --bot
  ```

### 4. Configuring Discord Bot Token (Terminal or GUI)

You can configure your Discord Bot Token using any of these convenient terminal methods:

- **Quick Save via Terminal:**
  ```powershell
  python main.py --set-token "YOUR_DISCORD_BOT_TOKEN"
  ```
- **Pass Directly to Launcher:**
  ```powershell
  .\run_lite.bat --token "YOUR_DISCORD_BOT_TOKEN"
  # or
  python main.py --lite --token "YOUR_DISCORD_BOT_TOKEN"
  ```
- **Environment Variable:**
  ```powershell
  $env:DISCORD_BOT_TOKEN="YOUR_DISCORD_BOT_TOKEN"
  ```
- **Interactive Terminal Prompt:** If no token is saved, running `run_lite.bat` will prompt you directly in the terminal before launching the GUI.

---

## ☁️ 24/7 Cloud Deployment (AWS EC2 / Lightsail)

The Discord Voice Bot can be deployed on an AWS EC2 instance or Lightsail VPS to run 24/7 independently of your local computer:

### 1. Install System Dependencies on Ubuntu
```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git ffmpeg libopus0 libopus-dev
```

### 2. Setup Project & Minimal Bot Dependencies
```bash
git clone https://github.com/dewanto-ar/woeyyy-audio.git
cd woeyyy-audio
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-bot.txt
```

### 3. Run as a Systemd Service (Auto-Start on Boot)
Copy the pre-configured [woeyyy-bot.service](woeyyy-bot.service) template:

```bash
sudo cp woeyyy-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now woeyyy-bot
```

Monitor live bot logs anytime:
```bash
journalctl -u woeyyy-bot -f
```

---

## 🧪 Automated Testing

Run the test suite to verify DSP processing, audio normalization, security sanitization, and favorite track CRUD:

```powershell
python -m unittest discover tests
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for more information.
