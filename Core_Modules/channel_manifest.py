"""Canonical playlist manifest utilities.

All generators should consume a ChannelManifest instead of parsing one M3U entry
at a time.  A channel is keyed by tvg-id (or its normalized name) and retains
every unique episode URL supplied by one or more playlists.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence


MANIFEST_VERSION = 1
_ATTRIBUTE_RE = re.compile(r'([\\w-]+)="([^"]*)"')
_EXTINF_TITLE_RE = re.compile(r",(.*)$")


def _slug(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "unnamed-channel"


def _attributes(extinf: str) -> dict[str, str]:
    return {key: value.strip() for key, value in _ATTRIBUTE_RE.findall(extinf)}


def _title_from_extinf(extinf: str) -> str:
    match = _EXTINF_TITLE_RE.search(extinf)
    return match.group(1).strip() if match else "Unnamed channel"


@dataclass
class Episode:
    url: str
    title: str = ""
    season: str | None = None
    episode_number: str | None = None
    duration_seconds: int | None = None

    def as_dict(self) -> dict:
        data = {"url": self.url, "title": self.title}
        if self.season is not None:
            data["season"] = self.season
        if self.episode_number is not None:
            data["episode_number"] = self.episode_number
        if self.duration_seconds is not None:
            data["duration_seconds"] = self.duration_seconds
        return data


@dataclass
class Channel:
    id: str
    name: str
    category: str = "General"
    logo: str = ""
    number: str | None = None
    tagline: str = ""
    logo_text: str = ""
    accent_color: str = ""
    episodes: list[Episode] = field(default_factory=list)

    def add_episode(self, episode: Episode) -> None:
        if episode.url and all(item.url != episode.url for item in self.episodes):
            self.episodes.append(episode)

    def as_dict(self) -> dict:
        data = {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "logo": self.logo,
            "episodes": [episode.as_dict() for episode in self.episodes],
        }
        for key, value in {
            "number": self.number,
            "tagline": self.tagline,
            "logo_text": self.logo_text,
            "accent_color": self.accent_color,
        }.items():
            if value:
                data[key] = value
        return data


class ChannelManifest:
    """A deterministic, de-duplicated collection of channels and episodes."""

    def __init__(self, channels: Iterable[Channel] = ()):
        self.channels: dict[str, Channel] = {channel.id: channel for channel in channels}

    def add_entry(
        self,
        *,
        url: str,
        name: str,
        tvg_id: str = "",
        category: str = "General",
        logo: str = "",
        title: str = "",
        **metadata: str,
    ) -> None:
        key = tvg_id.strip() or _slug(name)
        channel = self.channels.get(key)
        if channel is None:
            channel = Channel(
                id=key,
                name=name or key,
                category=category or "General",
                logo=logo,
                number=metadata.get("number"),
                tagline=metadata.get("tagline", ""),
                logo_text=metadata.get("logo_text", ""),
                accent_color=metadata.get("accent_color", ""),
            )
            self.channels[key] = channel
        else:
            # Preserve the first non-empty metadata; later playlists only fill gaps.
            channel.category = channel.category or category or "General"
            channel.logo = channel.logo or logo
        channel.add_episode(Episode(url=url.strip(), title=title or name))

    def merge(self, other: "ChannelManifest") -> "ChannelManifest":
        for incoming in other.channels.values():
            for episode in incoming.episodes:
                self.add_entry(
                    url=episode.url,
                    name=incoming.name,
                    tvg_id=incoming.id,
                    category=incoming.category,
                    logo=incoming.logo,
                    title=episode.title,
                    number=incoming.number or "",
                    tagline=incoming.tagline,
                    logo_text=incoming.logo_text,
                    accent_color=incoming.accent_color,
                )
        return self

    def as_dict(self) -> dict:
        return {
            "version": MANIFEST_VERSION,
            "channels": [channel.as_dict() for channel in self.channels.values()],
        }

    @classmethod
    def from_dict(cls, value: Mapping) -> "ChannelManifest":
        manifest = cls()
        for raw_channel in value.get("channels", []):
            channel = Channel(
                id=raw_channel.get("id") or _slug(raw_channel.get("name", "")),
                name=raw_channel.get("name", "Unnamed channel"),
                category=raw_channel.get("category", "General"),
                logo=raw_channel.get("logo", ""),
                number=str(raw_channel["number"]) if raw_channel.get("number") is not None else None,
                tagline=raw_channel.get("tagline", ""),
                logo_text=raw_channel.get("logo_text", raw_channel.get("logoText", "")),
                accent_color=raw_channel.get("accent_color", raw_channel.get("accentColor", "")),
            )
            for raw_episode in raw_channel.get("episodes", []):
                channel.add_episode(Episode(
                    url=raw_episode["url"],
                    title=raw_episode.get("title", channel.name),
                    season=str(raw_episode["season"]) if raw_episode.get("season") is not None else None,
                    episode_number=str(raw_episode.get("episode_number", raw_episode.get("episodeNumber"))) if raw_episode.get("episode_number", raw_episode.get("episodeNumber")) is not None else None,
                    duration_seconds=raw_episode.get("duration_seconds", raw_episode.get("durationSeconds")),
                ))
            manifest.channels[channel.id] = channel
        return manifest

    @classmethod
    def from_m3u(cls, content: str) -> "ChannelManifest":
        manifest = cls()
        pending: dict[str, str] | None = None
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#EXTINF"):
                attrs = _attributes(line)
                pending = {
                    "name": attrs.get("tvg-name") or _title_from_extinf(line),
                    "tvg_id": attrs.get("tvg-id", ""),
                    "category": attrs.get("group-title", "General"),
                    "logo": attrs.get("tvg-logo", ""),
                    "title": _title_from_extinf(line),
                }
                continue
            if not line.startswith("#") and pending:
                manifest.add_entry(url=line, **pending)
                pending = None
        return manifest

    @classmethod
    def from_sources(cls, sources: Sequence[str | Path]) -> "ChannelManifest":
        result = cls()
        for source in sources:
            raw = str(source)
            # Raw M3U text is a supported source; never treat it as a filesystem path.
            if "\n" in raw or raw.lstrip().startswith("#EXTM3U"):
                content = raw
            else:
                path = Path(raw)
                content = path.read_text(encoding="utf-8")
            result.merge(cls.from_m3u(content))
        return result

    def to_m3u(self) -> str:
        lines = ["#EXTM3U"]
        for channel in self.channels.values():
            attributes = [
                f'tvg-id="{channel.id}"',
                f'tvg-name="{channel.name}"',
                f'group-title="{channel.category}"',
            ]
            if channel.logo:
                attributes.append(f'tvg-logo="{channel.logo}"')
            for episode in channel.episodes:
                lines.append(f'#EXTINF:-1 {" ".join(attributes)},{episode.title or channel.name}')
                lines.append(episode.url)
        return "\n".join(lines) + "\n"


def load_manifest(path: str | Path) -> ChannelManifest:
    return ChannelManifest.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_manifest(manifest: ChannelManifest, path: str | Path) -> None:
    Path(path).write_text(json.dumps(manifest.as_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def manifest_to_template_channels(manifest: ChannelManifest) -> list[dict]:
    """Compatibility payload for legacy templates, including all episode URLs."""
    return [
        {
            "id": channel.id,
            "name": channel.name,
            "logo": channel.logo,
            "group": channel.category,
            "url": channel.episodes[0].url if channel.episodes else "",
            "episodes": [episode.as_dict() for episode in channel.episodes],
        }
        for channel in manifest.channels.values()
        if channel.episodes
    ]
