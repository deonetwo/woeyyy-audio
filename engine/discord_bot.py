"""
Woeyyy - Discord Voice Bot & Hi-Fi Audio Streaming Engine
Runs an embedded Discord Voice Bot inside a dedicated background asyncio thread.
Streams 48,000 Hz Stereo Opus audio directly into Discord voice channels with zero
Krisp noise-suppression cutoff, zero echo cancellation, and studio-grade clarity.

Features:
- Music Queue system (auto-play next track, /queue, /skip, /clear).
- Full YouTube Music (music.youtube.com) and regular YouTube URL/search support.
- Full Discord Slash Commands (/) for in-chat server control.
"""

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import warnings
from typing import Callable, Dict, List, Optional, Tuple

import discord
from discord import app_commands
from discord.ext import commands
import imageio_ffmpeg
import yt_dlp

# Suppress benign aiohttp unclosed connector ResourceWarnings on exit
warnings.filterwarnings("ignore", message=".*unclosed.*", category=ResourceWarning)
warnings.filterwarnings("ignore", message=".*Unclosed.*", category=ResourceWarning)

from engine.security import (
    secure_file_permissions,
    mask_token,
    sanitize_audio_target,
    is_safe_soundboard_path,
)



def ensure_opus_loaded() -> bool:
    """Ensure libopus C-library is loaded into discord.opus for voice streaming."""
    if discord.opus.is_loaded():
        return True

    discord_dir = os.path.dirname(discord.__file__)
    possible_locations = [
        "libopus.so.0",
        "libopus.so",
        "/usr/lib/x86_64-linux-gnu/libopus.so.0",
        "/usr/lib/libopus.so.0",
        "/usr/local/lib/libopus.so",
        os.path.join(discord_dir, "bin", "libopus-0.x64.dll"),
        os.path.join(discord_dir, "bin", "libopus-0.x86.dll"),
        "libopus-0.x64.dll",
        "libopus-0.dll",
        "opus",
    ]

    import ctypes.util
    found_lib = ctypes.util.find_library("opus")
    if found_lib:
        possible_locations.insert(0, found_lib)

    for loc in possible_locations:
        try:
            discord.opus.load_opus(loc)
            if discord.opus.is_loaded():
                return True
        except Exception:
            pass

    try:
        return discord.opus._load_default()
    except Exception:
        return False


def get_ffmpeg_binary() -> str:
    """Resolve FFmpeg binary path: prefer system ffmpeg first, then imageio_ffmpeg."""
    import shutil
    sys_ffmpeg = shutil.which("ffmpeg")
    if sys_ffmpeg:
        return sys_ffmpeg
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            if hasattr(os, "chmod") and sys.platform != "win32":
                try:
                    os.chmod(exe, 0o755)
                except Exception:
                    pass
            return exe
    except Exception:
        pass
    return "ffmpeg"


# Global FFmpeg binary path
FFMPEG_EXECUTABLE = get_ffmpeg_binary()

# YTDL options for fast, resilient audio stream extraction (bypasses datacenter bot blocks)
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "audioformat": "opus",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": False,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch1:",
    "source_address": "0.0.0.0",
    "extractor_args": {
        "youtube": {
            "player_client": ["android_music", "android", "tv_embedded", "ios"],
            "player_skip": ["web", "mweb"],
        }
    },
}

# Automatically bind cookies.txt if present to authenticate with YouTube
COOKIE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "cookies.txt"))
if os.path.exists(COOKIE_PATH):
    YTDL_OPTIONS["cookiefile"] = COOKIE_PATH
    YTDL_OPTIONS["remote_components"] = ["ejs:github"]
    YTDL_OPTIONS["format"] = "ba/b"

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


def normalize_youtube_url(query: str) -> str:
    """
    Normalize YouTube Music and YouTube URLs.
    Rewrites music.youtube.com -> www.youtube.com to avoid auth-gate throttling and guarantee
    flawless 48kHz Opus stream resolution.
    """
    target = query.strip()
    if "music.youtube.com" in target:
        target = target.replace("music.youtube.com", "www.youtube.com")
    return target


ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".bot_config.json"))


def load_saved_token() -> str:
    """
    Load Discord Bot Token with the following priority:
    1. OS Environment variable: DISCORD_BOT_TOKEN
    2. Local .env file
    3. Legacy .bot_config.json (auto-migrates to .env)
    """
    # 1. Check OS Environment variable
    tok = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if tok:
        return tok

    # 2. Check local .env file
    if os.path.exists(ENV_PATH):
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if line.startswith("DISCORD_BOT_TOKEN="):
                        val = line.split("=", 1)[1].strip().strip("\"'")
                        if val:
                            os.environ["DISCORD_BOT_TOKEN"] = val
                            return val
        except Exception:
            pass

    # 3. Fallback & migration from legacy .bot_config.json
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                legacy_tok = data.get("bot_token", "").strip()
                if legacy_tok:
                    save_token(legacy_tok)
                    try:
                        os.remove(CONFIG_PATH)
                    except Exception:
                        pass
                    return legacy_tok
        except Exception:
            pass

    return ""


def save_token(token: str):
    """
    Save Discord Bot Token to OS environment and persistent .env file.
    Secures file permissions via secure_file_permissions.
    """
    cleaned = token.strip().strip("\"'")
    os.environ["DISCORD_BOT_TOKEN"] = cleaned
    try:
        lines = []
        found = False
        if os.path.exists(ENV_PATH):
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                lines = f.readlines()
            for i, line in enumerate(lines):
                if line.strip().startswith("DISCORD_BOT_TOKEN="):
                    lines[i] = f"DISCORD_BOT_TOKEN={cleaned}\n"
                    found = True
                    break
        if not found:
            lines.append(f"DISCORD_BOT_TOKEN={cleaned}\n")

        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(lines)
        secure_file_permissions(ENV_PATH)

        # Remove legacy .bot_config.json if it exists
        if os.path.exists(CONFIG_PATH):
            try:
                os.remove(CONFIG_PATH)
            except Exception:
                pass
    except Exception as e:
        print(f"[DiscordBot] Failed to save token to .env: {e}")


def resolve_song_info(query_or_url: str) -> Tuple[bool, str, str]:
    """
    Resolve real track title and canonical URL using yt-dlp.
    Can run standalone without needing an active Discord bot gateway session.
    Returns: (success, resolved_title, canonical_url)
    """
    try:
        from engine.security import sanitize_audio_target
        target = normalize_youtube_url(query_or_url)
        is_safe, sanitized_target, _ = sanitize_audio_target(target)
        if not is_safe:
            return False, query_or_url, query_or_url

        if not (sanitized_target.startswith("http://") or sanitized_target.startswith("https://")):
            sanitized_target = f"ytsearch1:{sanitized_target}"

        with yt_dlp.YoutubeDL(YTDL_OPTIONS) as ydl:
            data = ydl.extract_info(sanitized_target, download=False)
            if "entries" in data and data["entries"]:
                data = data["entries"][0]
            title = data.get("title", query_or_url)
            url = data.get("webpage_url") or data.get("url") or sanitized_target
            return True, title, url
    except Exception as e:
        print(f"[DiscordBot] Notice: could not resolve song metadata: {e}")
        return False, query_or_url, query_or_url


class DiscordVoiceBot:
    """
    Thread-safe Discord Voice Bot controller with Song Queue and Slash Commands (/).
    Runs commands.Bot in a dedicated asyncio background loop.
    Communicates with GUI thread via threadsafe callbacks.
    """

    def __init__(self, on_status_change: Optional[Callable[[str, str], None]] = None):
        self.on_status_change = on_status_change

        self.client: Optional[commands.Bot] = None
        self.voice_client: Optional[discord.VoiceClient] = None

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

        self.is_connected = False
        self.is_in_voice = False
        self.is_playing = False
        self.is_paused = False

        self.current_title = "No audio playing"
        self.current_track: Optional[Dict[str, any]] = None
        self.queue: List[Dict[str, any]] = []  # List of track dicts
        self.volume = 1.0  # 1.0 = 100%

        self.available_channels: List[Tuple[str, int]] = []  # [(Display Name, channel_id)]
        self.current_channel_id: Optional[int] = None

        self.ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

    def _notify_status(self, status: str, detail: str = ""):
        """Notify GUI thread of connection/voice status update."""
        if self.on_status_change:
            try:
                self.on_status_change(status, detail)
            except Exception:
                pass

    def start(self, token: str):
        """Start the Discord bot in a background thread."""
        if self.is_connected or (self._thread and self._thread.is_alive()):
            self.stop()

        token = token.strip()
        if not token:
            self._notify_status("ERROR", "Token cannot be empty")
            return

        save_token(token)
        self._notify_status("CONNECTING", "Logging into Discord...")

        self._thread = threading.Thread(target=self._run_bot, args=(token,), daemon=True)
        self._thread.start()

    def _register_slash_commands(self):
        """Register all slash commands (/) on the bot's command tree."""
        bot = self.client

        @bot.tree.command(name="join", description="Hubungkan bot Woeyyy ke voice channel tempat kamu berada")
        async def cmd_join(interaction: discord.Interaction):
            if not interaction.user.voice or not interaction.user.voice.channel:
                await interaction.response.send_message(
                    "⚠️ Kamu harus masuk ke salah satu Voice Channel dulu!", ephemeral=True
                )
                return

            channel = interaction.user.voice.channel
            await interaction.response.defer(ephemeral=False)

            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.channel.id != channel.id:
                    await self.voice_client.move_to(channel)
            else:
                self.voice_client = await channel.connect(timeout=10.0, reconnect=True)

            self.is_in_voice = True
            self.current_channel_id = channel.id
            self._notify_status("VOICE_CONNECTED", channel.name)
            await interaction.followup.send(f"🔊 **Tersambung ke Voice Channel:** `#{channel.name}`")

        @bot.tree.command(name="play", description="Putar lagu dari YouTube / YouTube Music atau tambahkan ke antrean")
        @app_commands.describe(query="Judul lagu, link YouTube, atau link YouTube Music")
        async def cmd_play(interaction: discord.Interaction, query: str):
            # Auto-join if bot is not in a channel yet
            if not self.voice_client or not self.voice_client.is_connected():
                if interaction.user.voice and interaction.user.voice.channel:
                    channel = interaction.user.voice.channel
                    self.voice_client = await channel.connect(timeout=10.0, reconnect=True)
                    self.is_in_voice = True
                    self.current_channel_id = channel.id
                    self._notify_status("VOICE_CONNECTED", channel.name)
                else:
                    await interaction.response.send_message(
                        "⚠️ Bot belum masuk Voice Channel! Masuk ke VC lalu jalankan `/join` atau `/play`.",
                        ephemeral=True,
                    )
                    return

            await interaction.response.defer(ephemeral=False)
            self._notify_status("SEARCHING", f"Loading: {query[:35]}...")

            requester_name = interaction.user.display_name
            success, msg, is_queued, track = await self._async_enqueue_or_play(query, requester=requester_name)

            if not success:
                await interaction.followup.send(f"❌ {msg}")
                return

            title = track.get("title", query)
            dur = track.get("duration_str", "Live")

            if is_queued:
                pos = len(self.queue)
                await interaction.followup.send(
                    f"➕ **Ditambahkan ke Antrean (#{pos}):** `{title}` [{dur}]\n"
                    f"👤 *Diminta oleh:* {requester_name}"
                )
            else:
                await interaction.followup.send(
                    f"🎵 **Sedang Memutar:** `{title}` [{dur}]\n"
                    f"✨ *Kualitas: 48kHz Stereo Opus HD (Bebas Krisp / Noise Suppression)*\n"
                    f"👤 *Diminta oleh:* {requester_name}"
                )

        @bot.tree.command(name="skip", description="Lewati lagu yang sedang diputar dan putar lagu berikutnya di antrean")
        async def cmd_skip(interaction: discord.Interaction):
            if not self.is_playing and not self.is_paused:
                await interaction.response.send_message("⚠️ Tidak ada lagu yang sedang diputar.", ephemeral=True)
                return

            old_title = self.current_title
            next_track = self.queue[0] if self.queue else None
            self.skip()

            if next_track:
                await interaction.response.send_message(
                    f"⏭️ **Lagu dilewati:** `{old_title}`\n"
                    f"▶️ **Memutar berikutnya:** `{next_track['title']}` [{next_track['duration_str']}]"
                )
            else:
                await interaction.response.send_message(
                    f"⏭️ **Lagu dilewati:** `{old_title}`\n"
                    f"⏹️ *Antrean kosong, pemutaran selesai.*"
                )

        @bot.tree.command(name="queue", description="Lihat daftar antrean lagu yang akan diputar")
        async def cmd_queue(interaction: discord.Interaction):
            if not self.current_track and not self.queue:
                await interaction.response.send_message("📭 **Antrean lagu saat ini kosong.**", ephemeral=True)
                return

            lines = []
            if self.current_track:
                lines.append(f"▶️ **Sedang Diputar:** `{self.current_track['title']}` [{self.current_track['duration_str']}]")

            if self.queue:
                lines.append(f"\n📋 **Daftar Antrean ({len(self.queue)} Lagu):**")
                for i, t in enumerate(self.queue[:10], start=1):
                    lines.append(f"`{i}.` **{t['title']}** [{t['duration_str']}] *(by {t.get('requester', 'User')})*")
                if len(self.queue) > 10:
                    lines.append(f"... dan {len(self.queue) - 10} lagu lainnya.")

            await interaction.response.send_message("\n".join(lines))

        @bot.tree.command(name="clear", description="Kosongkan semua antrean lagu yang ada")
        async def cmd_clear(interaction: discord.Interaction):
            count = self.clear_queue()
            await interaction.response.send_message(f"🗑️ **Antrean telah dikosongkan.** ({count} lagu dihapus)")

        @bot.tree.command(name="pause", description="Pause lagu yang sedang diputar")
        async def cmd_pause(interaction: discord.Interaction):
            if self.voice_client and self.voice_client.is_playing():
                self.voice_client.pause()
                self.is_paused = True
                self._notify_status("PAUSED", self.current_title)
                await interaction.response.send_message("⏸️ **Pemutaran dijeda.**")
            else:
                await interaction.response.send_message("⚠️ Tidak ada audio yang sedang diputar.", ephemeral=True)

        @bot.tree.command(name="resume", description="Lanjutkan lagu yang dijeda")
        async def cmd_resume(interaction: discord.Interaction):
            if self.voice_client and self.voice_client.is_paused():
                self.voice_client.resume()
                self.is_paused = False
                self._notify_status("PLAYING", self.current_title)
                await interaction.response.send_message("▶️ **Pemutaran dilanjutkan.**")
            else:
                await interaction.response.send_message("⚠️ Tidak ada lagu yang sedang dijeda.", ephemeral=True)

        @bot.tree.command(name="stop", description="Hentikan lagu dan bersihkan antrean")
        async def cmd_stop(interaction: discord.Interaction):
            self.stop_playback()
            await interaction.response.send_message("⏹️ **Pemutaran dihentikan dan antrean dibersihkan.**")

        @bot.tree.command(name="volume", description="Ubah volume suara bot (0% - 150%)")
        @app_commands.describe(percentage="Persentase volume (contoh: 100)")
        async def cmd_volume(interaction: discord.Interaction, percentage: int):
            vol = max(0, min(150, percentage)) / 100.0
            self.set_volume(vol)
            await interaction.response.send_message(f"🔊 **Volume diatur ke:** `{percentage}%`")

        @bot.tree.command(name="soundboard", description="Putar efek suara instan ke Voice Channel")
        @app_commands.describe(sound="Pilih efek suara")
        @app_commands.choices(sound=[
            app_commands.Choice(name="🎺 Airhorn", value="airhorn"),
            app_commands.Choice(name="🥁 Ba-Dum-Tss", value="badumtss"),
            app_commands.Choice(name="🔔 Level Up", value="levelup"),
            app_commands.Choice(name="🎉 Tada", value="tada"),
            app_commands.Choice(name="🚨 Siren", value="siren"),
            app_commands.Choice(name="⚡ Laser", value="laser"),
        ])
        async def cmd_soundboard(interaction: discord.Interaction, sound: app_commands.Choice[str]):
            if not self.voice_client or not self.voice_client.is_connected():
                if interaction.user.voice and interaction.user.voice.channel:
                    channel = interaction.user.voice.channel
                    self.voice_client = await channel.connect(timeout=10.0, reconnect=True)
                    self.is_in_voice = True
                    self.current_channel_id = channel.id
                    self._notify_status("VOICE_CONNECTED", channel.name)
                else:
                    await interaction.response.send_message("⚠️ Bot harus berada di Voice Channel terlebih dahulu!", ephemeral=True)
                    return

            sounds_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "sounds"))
            file_path = os.path.join(sounds_dir, f"{sound.value}.wav")
            if not os.path.exists(file_path):
                sounds_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "sounds"))
                file_path = os.path.join(sounds_dir, f"{sound.value}.wav")

            if not os.path.exists(file_path):
                await interaction.response.send_message(f"❌ File soundboard `{sound.name}` belum ditemukan.", ephemeral=True)
                return

            self.play_sound(file_path, sound.name)
            await interaction.response.send_message(f"🔔 **Soundboard diputar:** `{sound.name}`")

        @bot.tree.command(name="leave", description="Keluarkan bot dari Voice Channel")
        async def cmd_leave(interaction: discord.Interaction):
            if self.voice_client and self.voice_client.is_connected():
                self.leave_voice_channel()
                await interaction.response.send_message("👋 **Bot telah keluar dari Voice Channel.**")
            else:
                await interaction.response.send_message("⚠️ Bot sedang tidak berada di Voice Channel mana pun.", ephemeral=True)

    def _run_bot(self, token: str):
        """Asyncio event loop runner."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        intents = discord.Intents.default()
        intents.guilds = True
        intents.voice_states = True
        intents.message_content = True

        self.client = commands.Bot(command_prefix="!", intents=intents)

        # Register slash commands
        self._register_slash_commands()

        @self.client.event
        async def on_ready():
            self.is_connected = True
            bot_name = str(self.client.user)
            print(f"[DiscordBot] Logged in successfully as {bot_name}")
            self._refresh_voice_channels_internal()
            self._notify_status("ONLINE", bot_name)

            # Sync slash commands (/) across all guilds for instant availability
            try:
                for guild in self.client.guilds:
                    self.client.tree.copy_global_to(guild=guild)
                    await self.client.tree.sync(guild=guild)
                await self.client.tree.sync()
                print("[DiscordBot] Slash commands (/) synced successfully to all servers!")
            except Exception as e:
                print(f"[DiscordBot] Note on syncing slash commands: {e}")

        @self.client.event
        async def on_voice_state_update(member, before, after):
            if member == self.client.user:
                if after.channel is None:
                    self.is_in_voice = False
                    self.voice_client = None
                    self.current_channel_id = None
                    self._notify_status("VOICE_DISCONNECTED", "Left voice channel")
                else:
                    self.is_in_voice = True
                    self.current_channel_id = after.channel.id
                    self._notify_status("VOICE_CONNECTED", after.channel.name)

        try:
            self._loop.run_until_complete(self.client.start(token))
        except Exception as e:
            self.is_connected = False
            print(f"[DiscordBot] Login failed or connection closed: {e}")
            self._notify_status("ERROR", str(e))
        finally:
            self.is_connected = False
            self.is_in_voice = False
            try:
                pending = [t for t in asyncio.all_tasks(self._loop) if not t.done()]
                for t in pending:
                    t.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                # Allow aiohttp connectors a brief moment to finish graceful teardown
                self._loop.run_until_complete(asyncio.sleep(0.25))
            except Exception:
                pass
            if not self._loop.is_closed():
                self._loop.close()

    def stop(self):
        """Disconnect and stop the Discord bot cleanly."""
        if not self.is_connected or not self._loop or not self.client:
            return

        async def _async_stop():
            try:
                if self.voice_client and self.voice_client.is_connected():
                    await self.voice_client.disconnect(force=True)
                if self.client:
                    await self.client.close()
                await asyncio.sleep(0.25)
            except Exception as e:
                print(f"[DiscordBot] Error during stop: {e}")

        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_async_stop(), self._loop)
            try:
                future.result(timeout=4.0)
            except Exception:
                pass

        self.is_connected = False
        self.is_in_voice = False
        self.voice_client = None
        self.queue.clear()
        self.current_track = None
        self._notify_status("OFFLINE", "Bot disconnected")

    def _refresh_voice_channels_internal(self):
        """Enumerate all visible voice channels in guilds where the bot is a member."""
        channels = []
        if self.client and self.client.guilds:
            for guild in self.client.guilds:
                for vc in guild.voice_channels:
                    label = f"{guild.name} ➔ #{vc.name}"
                    channels.append((label, vc.id))
        self.available_channels = channels

    def get_available_voice_channels(self) -> List[Tuple[str, int]]:
        """Return list of (DisplayName, ChannelID) for GUI dropdown."""
        if self.client and self.is_connected:
            self._refresh_voice_channels_internal()
        return self.available_channels

    def join_voice_channel(self, channel_id: int):
        """Connect the bot to a specific voice channel."""
        if not self.is_connected or not self._loop or not self.client:
            self._notify_status("ERROR", "Bot is not online")
            return

        async def _async_join():
            channel = self.client.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.VoiceChannel):
                self._notify_status("ERROR", "Channel not found")
                return

            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.channel.id == channel_id:
                    return
                await self.voice_client.move_to(channel)
            else:
                self.voice_client = await channel.connect(timeout=10.0, reconnect=True)

            self.is_in_voice = True
            self.current_channel_id = channel_id
            self._notify_status("VOICE_CONNECTED", channel.name)

        asyncio.run_coroutine_threadsafe(_async_join(), self._loop)

    def leave_voice_channel(self):
        """Disconnect the bot from its current voice channel."""
        if not self.voice_client or not self._loop:
            return

        async def _async_leave():
            if self.voice_client and self.voice_client.is_connected():
                if self.voice_client.is_playing():
                    self.voice_client.stop()
                await self.voice_client.disconnect(force=True)
            self.is_in_voice = False
            self.voice_client = None
            self.current_channel_id = None
            self.queue.clear()
            self.current_track = None
            self._notify_status("VOICE_DISCONNECTED", "Left voice channel")
            self._notify_status("QUEUE_UPDATED", "")

        asyncio.run_coroutine_threadsafe(_async_leave(), self._loop)

    async def _async_enqueue_or_play(self, query_or_url: str, requester: str = "Host") -> Tuple[bool, str, bool, Dict[str, any]]:
        """
        Extract stream info using yt-dlp with YouTube Music normalization.
        If something is playing, enqueue track. Otherwise, play immediately.
        Returns: (success, message, is_queued, track_dict)
        """
        try:
            target = normalize_youtube_url(query_or_url)
            is_safe, sanitized_target, reason = sanitize_audio_target(target)
            if not is_safe:
                return False, f"Keamanan: Tautan ditolak ({reason})", False, {}

            if not (sanitized_target.startswith("http://") or sanitized_target.startswith("https://")):
                sanitized_target = f"ytsearch1:{sanitized_target}"

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, lambda: self.ytdl.extract_info(sanitized_target, download=False)
            )

            if "entries" in data:
                entries = [e for e in data["entries"] if e]
                if not entries:
                    return False, f"Lagu tidak ditemukan: `{query_or_url}`", False, {}
                data = entries[0]

            stream_url = data.get("url")
            if not stream_url:
                return False, "Tidak dapat mengekstrak stream audio", False, {}

            title = data.get("title", query_or_url)
            sec = data.get("duration", 0) or 0
            dur_str = f"{sec // 60}:{sec % 60:02d}" if sec else "Live"

            track = {
                "url": stream_url,
                "title": title,
                "duration_sec": sec,
                "duration_str": dur_str,
                "webpage_url": data.get("webpage_url", query_or_url),
                "requester": requester,
                "http_headers": data.get("http_headers", {}),
            }

            # Check if playback is currently active
            if self.is_playing or self.is_paused:
                self.queue.append(track)
                self._notify_status("ENQUEUED", track.get("title", query_or_url))
                self._notify_status("QUEUE_UPDATED", "")
                return True, "Added to queue", True, track
            else:
                await self._async_play_track(track)
                return True, "Now playing", False, track

        except Exception as e:
            print(f"[DiscordBot] Failed to enqueue or play: {e}")
            return False, str(e), False, {}

    async def _async_play_track(self, track: Dict[str, any]):
        """Play track on the current voice_client."""
        if not self.voice_client or not self.voice_client.is_connected():
            return

        try:
            ensure_opus_loaded()
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()

            self.current_track = track
            self.current_title = track["title"]

            ffmpeg_bin = get_ffmpeg_binary()
            headers = track.get("http_headers") or {}
            user_agent = headers.get("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
            before_opts = (
                "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"
                f' -user_agent "{user_agent}"'
            )

            source = discord.FFmpegPCMAudio(
                track["url"],
                executable=ffmpeg_bin,
                before_options=before_opts,
                options="-vn",
                stderr=subprocess.PIPE,
            )
            transformer = discord.PCMVolumeTransformer(source, volume=self.volume)

            def _after_play(error):
                if error:
                    print(f"[DiscordBot] Playback error: {error}")
                    self._notify_status("ERROR", f"Playback error: {error}")
                else:
                    # Check if FFmpeg process crashed or exited abnormally
                    try:
                        proc = getattr(source, "_process", None)
                        if proc and proc.poll() is not None and proc.returncode != 0:
                            err_text = ""
                            if proc.stderr:
                                err_text = proc.stderr.read().decode("utf-8", errors="ignore").strip()
                            if err_text:
                                print(f"[DiscordBot] FFmpeg error (code {proc.returncode}):\n{err_text[-500:]}")
                    except Exception:
                        pass

                # Check if there are songs waiting in the queue
                if self.queue and self.voice_client and self.voice_client.is_connected():
                    next_song = self.queue.pop(0)
                    self._notify_status("QUEUE_UPDATED", "")
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(self._async_play_track(next_song), self._loop)
                else:
                    self.is_playing = False
                    self.is_paused = False
                    self.current_track = None
                    self.current_title = "No audio playing"
                    self._notify_status("PLAYBACK_STOPPED", "")
                    self._notify_status("QUEUE_UPDATED", "")

            self.voice_client.play(transformer, after=_after_play)
            self.is_playing = True
            self.is_paused = False
            self._notify_status("PLAYING", track["title"])
            self._notify_status("QUEUE_UPDATED", "")
        except discord.opus.OpusNotLoaded:
            err_msg = "Opus library not found. Run: sudo apt install -y libopus0 libopus-dev"
            print(f"[DiscordBot] {err_msg}")
            self.is_playing = False
            self.is_paused = False
            self.current_track = None
            self._notify_status("ERROR", err_msg)
        except Exception as e:
            err_msg = str(e) or type(e).__name__
            print(f"[DiscordBot] Failed to start playback: {err_msg} ({type(e).__name__})")
            self.is_playing = False
            self.is_paused = False
            self.current_track = None
            self._notify_status("ERROR", f"Failed to play: {err_msg}")

    def play_music(self, query_or_url: str):
        """Send song request from GUI or caller into queue/playback pipeline."""
        if not self.is_in_voice or not self.voice_client or not self._loop:
            self._notify_status("ERROR", "Bot is not in a voice channel")
            return

        self._notify_status("SEARCHING", f"Loading: {query_or_url[:35]}...")

        async def _run():
            success, msg, is_q, track = await self._async_enqueue_or_play(query_or_url, requester="GUI Host")
            if not success:
                self._notify_status("ERROR", msg)
            elif is_q:
                self._notify_status("ENQUEUED", track.get("title", query_or_url))

        asyncio.run_coroutine_threadsafe(_run(), self._loop)

    def skip(self) -> Optional[str]:
        """Skip currently playing track and advance queue."""
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            old_title = self.current_title
            self.voice_client.stop()
            return old_title
        return None

    def clear_queue(self) -> int:
        """Clear upcoming songs from queue."""
        count = len(self.queue)
        self.queue.clear()
        self._notify_status("QUEUE_UPDATED", "")
        return count

    def get_queue(self) -> List[Dict[str, any]]:
        """Return list of queued tracks."""
        return list(self.queue)

    def play_sound(self, file_path: str, title: Optional[str] = None):
        """Play a local soundboard audio file into the Discord voice channel."""
        if not self.is_in_voice or not self.voice_client or not self._loop:
            return

        if not os.path.exists(file_path):
            print(f"[DiscordBot] Sound file not found: {file_path}")
            return

        if not is_safe_soundboard_path(file_path):
            print(f"[Security] Blocked unauthorized sound path traversal: {file_path}")
            return

        display_name = title or os.path.splitext(os.path.basename(file_path))[0].title()

        async def _async_play_sound():
            try:
                ensure_opus_loaded()
                if self.voice_client.is_playing() or self.voice_client.is_paused():
                    self.voice_client.stop()

                source = discord.FFmpegPCMAudio(
                    file_path,
                    executable=FFMPEG_EXECUTABLE,
                    options="-vn",
                )
                transformer = discord.PCMVolumeTransformer(source, volume=self.volume)

                def _after_sound(error):
                    if error:
                        print(f"[DiscordBot] Sound playback error: {error}")
                        self._notify_status("ERROR", f"Sound error: {error}")

                    # Check if there is a song in queue to resume
                    if self.queue:
                        next_song = self.queue.pop(0)
                        self._notify_status("QUEUE_UPDATED", "")
                        if self._loop and self._loop.is_running():
                            asyncio.run_coroutine_threadsafe(self._async_play_track(next_song), self._loop)
                    else:
                        self.is_playing = False
                        self._notify_status("PLAYBACK_STOPPED", "")

                self.voice_client.play(transformer, after=_after_sound)
                self.is_playing = True
                self.current_title = f"🔔 {display_name}"
                self._notify_status("PLAYING", self.current_title)

            except Exception as e:
                print(f"[DiscordBot] Soundboard play error: {e}")
                self._notify_status("ERROR", f"Soundboard error: {e}")

        asyncio.run_coroutine_threadsafe(_async_play_sound(), self._loop)

    def pause(self):
        """Pause current playback."""
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            self.is_paused = True
            self._notify_status("PAUSED", self.current_title)

    def resume(self):
        """Resume paused playback."""
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            self.is_paused = False
            self._notify_status("PLAYING", self.current_title)

    def stop_playback(self):
        """Stop current audio playback and clear queue."""
        self.queue.clear()
        self.current_track = None
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()
        self.is_playing = False
        self.is_paused = False
        self.current_title = "No audio playing"
        self._notify_status("PLAYBACK_STOPPED", "")
        self._notify_status("QUEUE_UPDATED", "")

    def set_volume(self, volume: float):
        """Update playback volume (0.0 to 1.5)."""
        self.volume = max(0.0, min(1.5, float(volume)))
        if self.voice_client and hasattr(self.voice_client, "source") and self.voice_client.source:
            try:
                self.voice_client.source.volume = self.volume
            except Exception:
                pass
