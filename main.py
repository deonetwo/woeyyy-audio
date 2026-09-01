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
        help="Run in interactive terminal/CLI mode instead of the desktop GUI",
    )
    args = parser.parse_args()

    if args.cli:
        from run_mic_boost import run_interactive_cli
        run_interactive_cli()
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
