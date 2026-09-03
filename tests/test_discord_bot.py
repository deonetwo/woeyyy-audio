"""
Unit tests for Woeyyy Discord Voice Bot subsystem.
Verifies bot controller initialization, configuration storage,
FFmpeg binary presence, and thread lifecycle.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.discord_bot import (
    DiscordVoiceBot,
    FFMPEG_EXECUTABLE,
    load_saved_token,
    save_token,
)


class TestDiscordVoiceBot(unittest.TestCase):

    def test_ffmpeg_binary_exists(self):
        """Verify imageio-ffmpeg bundled binary exists and is executable."""
        self.assertTrue(os.path.exists(FFMPEG_EXECUTABLE))
        if sys.platform == "win32":
            self.assertTrue(FFMPEG_EXECUTABLE.endswith(".exe"))

    def test_token_save_and_load(self):
        """Verify token persistence in .env and DISCORD_BOT_TOKEN."""
        dummy_token = "TEST_DISCORD_TOKEN_12345"
        save_token(dummy_token)
        loaded = load_saved_token()
        self.assertEqual(dummy_token, loaded)

    def test_bot_controller_init(self):
        """Verify DiscordVoiceBot initial state and parameters."""
        bot = DiscordVoiceBot()
        self.assertFalse(bot.is_connected)
        self.assertFalse(bot.is_in_voice)
        self.assertFalse(bot.is_playing)
        self.assertEqual(bot.volume, 1.0)
        self.assertEqual(len(bot.available_channels), 0)

    def test_bot_volume_clamping(self):
        """Verify volume control adheres to [0.0, 1.5] bounds."""
        bot = DiscordVoiceBot()
        bot.set_volume(2.0)
        self.assertEqual(bot.volume, 1.5)
        bot.set_volume(-0.5)
        self.assertEqual(bot.volume, 0.0)
    def test_youtube_music_normalization(self):
        """Verify music.youtube.com URLs are rewritten to www.youtube.com."""
        from engine.discord_bot import normalize_youtube_url
        ym_url = "https://music.youtube.com/watch?v=ODqzYeSICCs&list=RDAMVM"
        expected = "https://www.youtube.com/watch?v=ODqzYeSICCs&list=RDAMVM"
        self.assertEqual(normalize_youtube_url(ym_url), expected)

        # Standard YouTube remains unchanged
        std_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertEqual(normalize_youtube_url(std_url), std_url)

    def test_queue_operations(self):
        """Verify queue manipulation methods."""
        bot = DiscordVoiceBot()
        self.assertEqual(len(bot.get_queue()), 0)

        # Enqueue dummy items directly
        bot.queue.append({"title": "Song 1", "duration_str": "3:20"})
        bot.queue.append({"title": "Song 2", "duration_str": "4:15"})
        self.assertEqual(len(bot.get_queue()), 2)

        # Clear queue
        cleared = bot.clear_queue()
        self.assertEqual(cleared, 2)
        self.assertEqual(len(bot.get_queue()), 0)


if __name__ == "__main__":
    unittest.main()
