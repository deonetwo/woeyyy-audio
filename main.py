"""
Woeyyy - Real-Time Audio Enhancer & Soundboard
Main entrypoint launcher.
"""

import argparse
import sys


def main():
    parser = argparse.ArgumentParser(description="Woeyyy - Real-Time Audio Enhancer & Soundboard")
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Run interactive Microphone Enhancer CLI in terminal",
    )
    parser.add_argument(
        "--bot",
        action="store_true",
        help="Run headless Discord Hi-Fi Voice Bot in lightweight terminal mode",
    )
    parser.add_argument(
        "--lite",
        action="store_true",
        help="Run Woeyyy Lite (minimalist Mic Boost & on-demand Discord bot)",
    )
    parser.add_argument(
        "--token",
        type=str,
        default="",
        help="Discord Bot Token (saves to .bot_config.json)",
    )
    parser.add_argument(
        "--set-token",
        type=str,
        default="",
        help="Quickly save Discord Bot Token from terminal and exit",
    )
    args = parser.parse_args()

    if args.set_token:
        from engine.discord_bot import save_token, mask_token
        save_token(args.set_token)
        print(f"[+] Successfully saved Discord Bot Token: {mask_token(args.set_token)}")
        sys.exit(0)

    if args.token:
        from engine.discord_bot import save_token, mask_token
        save_token(args.token)
        print(f"[*] Loaded Discord Bot Token: {mask_token(args.token)}")

    if args.bot:
        from bot_cli import main as run_bot_cli
        run_bot_cli()
    elif args.cli:
        from run_mic_boost import run_interactive_cli
        run_interactive_cli()
    elif args.lite:
        from gui_lite import main as run_gui_lite
        run_gui_lite()
    else:
        try:
            import customtkinter  # noqa: F401
            from gui import main as run_gui
            run_gui()
        except ImportError:
            print("[INFO] customtkinter not found. Falling back to terminal CLI mode...")
            from run_mic_boost import run_interactive_cli
            run_interactive_cli()


if __name__ == "__main__":
    main()
