"""Unit tests for Favorite Music system in Woeyyy Lite."""

import unittest
from gui_lite import WoeyyyLiteApp


class TestFavoritesSystem(unittest.TestCase):
    def test_favorites_normalization_and_crud(self):
        """Test favorites list normalization, addition, and removal logic."""
        app = WoeyyyLiteApp.__new__(WoeyyyLiteApp)
        app.cfg = {
            "favorite_tracks": [
                "Niki - Anaheim",
                {"title": "Coldplay - Yellow", "query": "https://www.youtube.com/watch?v=yKNxeF4KMsY"},
            ]
        }

        # 1. Test normalization
        favs = app._get_favorites_list()
        self.assertEqual(len(favs), 2)
        self.assertEqual(favs[0]["title"], "Niki - Anaheim")
        self.assertEqual(favs[0]["query"], "Niki - Anaheim")
        self.assertEqual(favs[1]["title"], "Coldplay - Yellow")
        self.assertTrue(favs[1]["query"].startswith("https://"))

        # 2. Test duplicate detection
        titles = [f["title"].lower() for f in favs]
        self.assertIn("niki - anaheim", titles)
        self.assertIn("coldplay - yellow", titles)

        # 3. Test deletion
        favs = [f for f in favs if f["title"] != "Niki - Anaheim"]
        self.assertEqual(len(favs), 1)
        self.assertEqual(favs[0]["title"], "Coldplay - Yellow")

        # 4. Test empty handling
        app.cfg["favorite_tracks"] = []
        self.assertEqual(app._get_favorites_list(), [])


if __name__ == "__main__":
    unittest.main()
