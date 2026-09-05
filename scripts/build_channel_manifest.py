#!/usr/bin/env python3
"""Build the canonical manifest and derived M3U playlist.

Examples:
  python scripts/build_channel_manifest.py playlist.m3u Sample_Playlists
  python scripts/build_channel_manifest.py --manifest channel_manifest.json playlist.m3u
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Core_Modules"))

from channel_manifest import ChannelManifest, load_manifest, save_manifest


def playlist_sources(values: list[str]) -> list[Path]:
    sources: list[Path] = []
    for value in values:
        path = Path(value)
        if path.is_dir():
            sources.extend(sorted(path.rglob("*.m3u")))
            sources.extend(sorted(path.rglob("*.m3u8")))
        else:
            sources.append(path)
    return sources


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources", nargs="*", help="M3U files or directories of M3U files")
    parser.add_argument("--manifest", default="channel_manifest.json", help="Canonical manifest path")
    parser.add_argument("--playlist", default="playlist.m3u", help="Generated M3U path")
    parser.add_argument("--from-manifest", action="store_true", help="Only regenerate playlist from manifest")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    if args.from_manifest:
        manifest = load_manifest(manifest_path)
    else:
        sources = playlist_sources(args.sources)
        if not sources:
            parser.error("provide at least one M3U source, or use --from-manifest")
        missing = [str(path) for path in sources if not path.exists()]
        if missing:
            parser.error("missing sources: " + ", ".join(missing))
        manifest = ChannelManifest.from_sources(sources)
        save_manifest(manifest, manifest_path)

    Path(args.playlist).write_text(manifest.to_m3u(), encoding="utf-8")
    episodes = sum(len(channel.episodes) for channel in manifest.channels.values())
    print(f"Wrote {manifest_path} and {args.playlist}: {len(manifest.channels)} channels, {episodes} unique episodes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
