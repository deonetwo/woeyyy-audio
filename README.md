# Woeyyy Audio Suite

A low-latency audio utility and Discord Hi-Fi voice streaming bot built with Python.

---

## Fitur Utama

- **Microphone Booster:** Software amplification (+0 dB s.d. +36 dB) dengan dynamic soft-knee limiter (-0.1 dBFS ceiling).
- **Discord Voice Bot:** 48kHz Stereo Opus direct playback dengan slash commands (`/play`, `/skip`, `/queue`, dll).
- **Favorite Music (Lite):** Bookmark dan antrekan lagu favorit dengan 1 klik.
- **Headless Cloud Daemon:** Mode background service untuk server Ubuntu / AWS EC2.

---

## Pilihan Mode

| Mode | Deskripsi | Perintah Menjalankan |
|---|---|---|
| **Woeyyy Lite** | Aplikasi desktop compact (Mic Boost + Discord Bot) | `.\run_lite.bat` atau `python main.py --lite` |
| **Woeyyy Full** | Studio lengkap (Mic Boost + Soundboard + Vocal EQ) | `.\run.bat` atau `python main.py` |
| **Headless Bot** | Mode terminal tanpa GUI (Server Linux 24/7) | `python main.py --bot` atau `python bot_cli.py --daemon` |

---

## Menjalankan di Lokal (Windows)

### 1. Prasyarat
- Windows 10 / 11
- Python 3.10 s.d. 3.14

### 2. Instalasi
```powershell
git clone https://github.com/dewanto-ar/woeyyy-audio.git
cd woeyyy-audio

# Buat dan aktifkan virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# Install dependency
pip install -r requirements.txt
```

### 3. Konfigurasi Token Discord
Simpan token bot Discord via terminal:
```powershell
python main.py --set-token "TOKEN_DISCORD_KAMU"
```
*(Atau buat file `.env` di folder project dengan isi `DISCORD_BOT_TOKEN=TOKEN_DISCORD_KAMU`)*

### 4. Menjalankan Aplikasi
Pilih salah satu sesuai mode yang diinginkan:
```powershell
# Versi Lite (Rekomendasi untuk sehari-hari)
.\run_lite.bat

# Versi Full Studio
.\run.bat

# Versi Terminal Bot
.\run_bot.bat
```

---

## Menjalankan di Server (AWS EC2 / Ubuntu Linux)

### 1. Install Dependency Sistem
```bash
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git ffmpeg libopus0 libopus-dev
```

### 2. Setup Project
```bash
git clone https://github.com/dewanto-ar/woeyyy-audio.git
cd woeyyy-audio
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-bot.txt
```

### 3. Konfigurasi Token & Cookies
Buat file `.env` di dalam folder project:
```bash
echo "DISCORD_BOT_TOKEN=TOKEN_DISCORD_KAMU" > .env
```
*(Opsional: letakkan file `cookies.txt` di root folder project untuk mengatasi pembatasan login YouTube).*

### 4. Menjalankan 24/7 dengan Systemd
Pasang service agar bot otomatis berjalan di latar belakang dan otomatis aktif saat server boot:

```bash
sudo cp woeyyy-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now woeyyy-bot
```

### 5. Manajemen Service
```bash
# Cek status bot
sudo systemctl status woeyyy-bot

# Lihat log real-time
sudo journalctl -u woeyyy-bot -f

# Restart bot
sudo systemctl restart woeyyy-bot

# Hentikan bot
sudo systemctl stop woeyyy-bot
```

---

## Slash Commands Discord

| Perintah | Deskripsi |
|---|---|
| `/play <judul/url>` | Putar lagu dari YouTube / YouTube Music atau tambahkan ke antrean |
| `/skip` | Lewati lagu yang sedang diputar |
| `/pause` | Jeda pemutaran lagu |
| `/resume` | Lanjutkan lagu yang dijeda |
| `/queue` | Lihat daftar antrean lagu |
| `/clear` | Kosongkan seluruh antrean lagu |
| `/stop` | Hentikan pemutaran dan bersihkan antrean |
| `/join` | Sambungkan bot ke voice channel |
| `/leave` | Keluarkan bot dari voice channel |
| `/volume <persen>` | Atur volume suara bot (0 - 150%) |

---

## Automated Testing

Jalankan test suite untuk memverifikasi fungsionalitas audio processing, sanitasi URL, dan bot:
```powershell
python -m unittest discover tests
```

---

## Lisensi
MIT License
