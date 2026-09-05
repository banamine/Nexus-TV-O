import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "Core_Modules"))
from channel_manifest import ChannelManifest


FIRST = """#EXTM3U
#EXTINF:-1 tvg-id="west" tvg-name="Westerns" group-title="Drama",Episode one
https://example.test/one.mp4
#EXTINF:-1 tvg-id="west" tvg-name="Westerns" group-title="Drama",Episode two
https://example.test/two.mp4
"""

SECOND = """#EXTM3U
#EXTINF:-1 tvg-id="west" tvg-name="Westerns" group-title="Drama",Duplicate
https://example.test/two.mp4
#EXTINF:-1 tvg-id="west" tvg-name="Westerns" group-title="Drama",Episode three
https://example.test/three.mp4
"""


class ChannelManifestTests(unittest.TestCase):
    def test_groups_and_deduplicates_entries_from_many_playlists(self):
        manifest = ChannelManifest.from_sources([FIRST, SECOND])
        self.assertEqual(list(manifest.channels), ["west"])
        self.assertEqual(
            [episode.url for episode in manifest.channels["west"].episodes],
            ["https://example.test/one.mp4", "https://example.test/two.mp4", "https://example.test/three.mp4"],
        )

    def test_m3u_round_trip_retains_every_episode(self):
        manifest = ChannelManifest.from_sources([FIRST, SECOND])
        restored = ChannelManifest.from_m3u(manifest.to_m3u())
        self.assertEqual(
            [episode.url for episode in restored.channels["west"].episodes],
            [episode.url for episode in manifest.channels["west"].episodes],
        )

    def test_json_round_trip_retains_metadata(self):
        manifest = ChannelManifest.from_sources([FIRST])
        restored = ChannelManifest.from_dict(json.loads(json.dumps(manifest.as_dict())))
        self.assertEqual(restored.channels["west"].name, "Westerns")
        self.assertEqual(len(restored.channels["west"].episodes), 2)


if __name__ == "__main__":
    unittest.main()
