"""
Woeyyy - Headless Discord Hi-Fi Voice Bot (Non-GUI / CLI Mode)
Ultra-lightweight background audio bot for Discord servers.
Streams 48kHz stereo Opus with zero GUI overhead (~25MB RAM).
"""

import argparse
import os
import signal
import sys
import threading
import time
from typing import Optional

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from engine.discord_bot import DiscordVoiceBot, load_saved_token, save_token
from engine.security import SingleInstanceLock, mask_token, is_safe_soundboard_path


def status_callback(status: str, detail: str):
    """Handle status updates from the Discord voice bot."""
    if status in ("ONLINE", "CONNECTED"):
        print(f"\n[+] Logged in successfully: {detail}")
    elif status in ("DISCONNECTED", "OFFLINE"):
        print(f"\n[-] Bot disconnected from Discord.")
    elif status == "VOICE_CONNECTED":
        print(f"\n[+] Joined Voice Channel: #{detail}")
    elif status == "VOICE_DISCONNECTED":
        print(f"\n[-] Left Voice Channel ({detail})")
    elif status == "PLAYING":
        print(f"\n[🎵 Now Playing] {detail}")
    elif status == "PAUSED":
        print(f"\n[⏸️ Paused] {detail}")
    elif status == "PLAYBACK_STOPPED":
        print(f"\n[⏹️ Playback Finished] Voice channel is idle.")
    elif status == "SEARCHING":
        print(f"[*] {detail}")
    elif status == "ERROR":
        print(f"\n[⚠️ Error] {detail}")
    elif status == "QUEUE_UPDATED":
        pass


def print_banner():
    print("=" * 62)
    print("   🤖 Woeyyy Discord Hi-Fi Voice Bot (Headless / Non-GUI)   ")
    print("   Studio 48kHz Opus • Full Slash Commands (/) • Zero-Lag   ")
    print("=" * 62)


def print_help():
    print("\nAvailable Terminal Commands:")
    print("  p, play <query/url>   - Play song or YouTube Music in VC")
    print("  j, join [channel_name]- Join voice channel (shows list if omitted)")
    print("  l, leave              - Leave current voice channel")
    print("  s, skip               - Skip currently playing song")
    print("  q, queue              - Show upcoming song queue")
    print("  pause                 - Pause playback")
    print("  resume                - Resume playback")
    print("  stop                  - Stop audio playback")
    print("  v, vol <0-100>        - Adjust playback volume")
    print("  sb <name>             - Play soundboard (airhorn, badumtss, tada, etc.)")
    print("  help                  - Show this help list")
    print("  exit, quit            - Disconnect and exit")
    print("\n*Tip: Users inside Discord can also use /play, /skip, /queue directly in chat!\n")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Woeyyy - Headless Discord Hi-Fi Voice Bot")
    parser.add_argument("--daemon", action="store_true", help="Run in headless non-interactive daemon mode (Systemd / Cloud)")
    parser.add_argument("--token", type=str, default="", help="Discord Bot Token (or set DISCORD_BOT_TOKEN env var)")
    args = parser.parse_args()

    is_daemon = args.daemon or (not sys.stdin.isatty())

    lock = SingleInstanceLock()
    if not lock.acquire():
        print("\n[Security Alert] Another session of Woeyyy is already active on this system.")
        print("                 Only one instance is permitted to prevent hardware/token conflicts.")
        SingleInstanceLock.focus_existing_window("Woeyyy")
        sys.exit(0)

    bot = None
    try:
        print_banner()

        # 1. Resolve Bot Token
        token = args.token or os.environ.get("DISCORD_BOT_TOKEN")
        if not token or token.strip() == "YOUR_BOT_TOKEN_HERE":
            token = load_saved_token()

        if not token or token.strip() == "YOUR_BOT_TOKEN_HERE":
            if is_daemon:
                print("[ERROR] Bot token not provided. Please set your real Discord Bot Token:")
                print("        1. Edit /etc/systemd/system/woeyyy-bot.service and set Environment=\"DISCORD_BOT_TOKEN=...\"")
                print("        2. Or pass --token <your_token> in ExecStart")
                sys.exit(1)
            else:
                print("[!] No saved bot token found.")
                token = input("    Enter your Discord Bot Token: ").strip()
                if not token or token == "YOUR_BOT_TOKEN_HERE":
                    print("[ERROR] Token cannot be empty or placeholder. Exiting.")
                    sys.exit(1)
                save_token(token)
        else:
            print(f"[*] Using Bot Token: {mask_token(token)}")
            if not is_daemon and not args.token and not os.environ.get("DISCORD_BOT_TOKEN"):
                ans = input("    Press Enter to use this token, or type a new one: ").strip()
                if ans:
                    token = ans
                    save_token(token)

        # 2. Instantiate and start bot
        bot = DiscordVoiceBot(on_status_change=status_callback)
        print("\n[*] Connecting to Discord Gateway...")
        bot.start(token)

        # Wait for login
        time.sleep(2.5)

        if is_daemon:
            print("[*] Running in headless daemon mode.")
            print("[*] Bot is active 24/7! Control via Discord Slash Commands (/) in chat:")
            print("    /play <query/url>  - Stream music into voice channel")
            print("    /skip              - Skip current song")
            print("    /queue             - View upcoming song queue")
            print("    /join              - Summon bot to your voice channel")
            print("    /leave             - Disconnect bot from voice")
            print("    /stop              - Stop playback")

            stop_event = threading.Event()

            def _handle_signal(sig, frame):
                print(f"\n[*] Received signal {sig}, terminating gracefully...")
                stop_event.set()

            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
            stop_event.wait()
            return

        print_help()

        # 3. Interactive CLI loop
        while True:
            try:
                cmd_line = input("woeyyy-bot> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not cmd_line:
                continue

            parts = cmd_line.split(maxsplit=1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd in ("exit", "quit", "q!"):
                print("[*] Shutting down bot...")
                break

            elif cmd == "help":
                print_help()

            elif cmd in ("j", "join"):
                channels = bot.get_available_voice_channels()
                if not channels:
                    print("[!] No voice channels found. Make sure the bot is invited to your Discord server.")
                    continue

                if not arg:
                    print("\nAvailable Voice Channels:")
                    for idx, (ch_name, ch_id) in enumerate(channels, 1):
                        print(f"  [{idx}] {ch_name} (ID: {ch_id})")
                    choice = input("Enter channel number or name to join: ").strip()
                    if choice.isdigit() and 1 <= int(choice) <= len(channels):
                        target_id = channels[int(choice) - 1][1]
                        bot.join_voice_channel(target_id)
                    else:
                        match = [cid for name, cid in channels if choice.lower() in name.lower()]
                        if match:
                            bot.join_voice_channel(match[0])
                        else:
                            print("[!] Voice channel not found.")
                else:
                    match = [cid for name, cid in channels if arg.lower() in name.lower()]
                    if match:
                        bot.join_voice_channel(match[0])
                    else:
                        print(f"[!] Voice channel matching '{arg}' not found.")

            elif cmd in ("l", "leave"):
                if bot.is_in_voice:
                    bot.leave_voice_channel()
                else:
                    print("[!] Bot is not in any voice channel.")

            elif cmd in ("p", "play"):
                if not arg:
                    print("[!] Please provide a song title or URL: play <title/url>")
                    continue
                if not bot.is_in_voice:
                    print("[!] Bot is not connected to a Voice Channel. Use 'join' first!")
                    continue
                bot.play_music(arg)

            elif cmd in ("s", "skip"):
                skipped = bot.skip()
                if skipped:
                    print(f"[*] Skipped: {skipped}")
                else:
                    print("[!] Nothing currently playing.")

            elif cmd == "pause":
                bot.pause()
                print("[*] Paused playback.")

            elif cmd == "resume":
                bot.resume()
                print("[*] Resumed playback.")

            elif cmd == "stop":
                bot.stop_playback()
                print("[*] Stopped playback.")

            elif cmd in ("q", "queue"):
                q = bot.get_queue()
                if not q:
                    print("[*] The song queue is currently empty.")
                else:
                    print(f"\n--- Current Queue ({len(q)} tracks) ---")
                    for i, t in enumerate(q, 1):
                        print(f"  {i}. {t['title']} [{t['duration_str']}] (Requested by: {t['requester']})")
                    print("-----------------------------------")

            elif cmd in ("v", "vol", "volume"):
                if not arg:
                    print(f"[*] Current volume: {int(bot.volume * 100)}%")
                else:
                    try:
                        val = float(arg)
                        if val > 1.0:
                            val = val / 100.0  # Convert 0-100 to 0.0-1.0
                        val = max(0.0, min(1.0, val))
                        bot.set_volume(val)
                        print(f"[*] Volume set to {int(val * 100)}%")
                    except ValueError:
                        print("[!] Invalid volume. Enter a number between 0 and 100.")

            elif cmd == "sb":
                if not arg:
                    print("Available presets: airhorn, badumtss, buzzer, coin, levelup, tada, siren, laser")
                    continue
                sounds_dir = os.path.join(BASE_DIR, "sounds")
                sound_file = os.path.join(sounds_dir, f"{arg.lower()}.wav")
                if not is_safe_soundboard_path(sound_file, [sounds_dir]):
                    print(f"[Security] Blocked unauthorized sound path: {sound_file}")
                    continue
                if os.path.exists(sound_file):
                    bot.play_sound(sound_file, arg.title())
                else:
                    print(f"[!] Sound preset '{arg}' not found in {sounds_dir}")

            else:
                print(f"[!] Unknown command '{cmd}'. Type 'help' for available commands.")

    finally:
        if bot is not None:
            print("\n[*] Disconnecting bot and cleaning up...")
            bot.stop()
            print("[+] Bot stopped safely. Goodbye!")
        if lock is not None:
            lock.release()


if __name__ == "__main__":
    main()
