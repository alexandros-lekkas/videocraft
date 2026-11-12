"""The committed map of Minecraft's sounds and music (minecraft.toml, music.toml), read without any game asset.

    events() -> {id: {category, variants, seconds, tags, original}}     tracks() -> {file: {events, seconds, mood, bpm, …}}
    palette() -> {name: {about, original, pick | sequence | roll}}      best() -> {tag: [ids preferred, in order]}
    candidates("footstep wood") -> [ids], best first                   original_of(event) -> library name or None

A query is one or more tags (space, comma or + separated): an event must carry all of them. Ranking: the curated
[best] list of the first tag, then events whose tags say the most about the query (fewest other tags), then the
shorter id. docs/SOUNDS.md explains the map; build.py (`videocraft audio catalog --refresh`) regenerates it.
"""
import re
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent

_cache = {}


def _load(name):
    if name not in _cache:
        path = HERE / name
        _cache[name] = tomllib.loads(path.read_text()) if path.exists() else {}
    return _cache[name]


def reload():
    _cache.clear()


def events():
    return _load('minecraft.toml').get('events', {})


def best():
    return _load('minecraft.toml').get('best', {})


def palette():
    return _load('minecraft.toml').get('palette', {})


def tracks():
    return _load('music.toml').get('track', {})


def bare(event_id):
    return event_id.split(':', 1)[1] if event_id.startswith('minecraft:') else event_id


def event(event_id):
    return events().get(bare(event_id))


def parse_tags(query):
    if isinstance(query, (list, tuple)):
        words = [w for q in query for w in parse_tags(q)]
    else:
        words = [w for w in re.split(r'[\s,+]+', str(query).strip().lower()) if w]
    return words


def candidates(query, limit=None):
    """Event ids carrying every tag of the query, best first."""
    tags = parse_tags(query)
    if not tags:
        return []
    rank = {e: i for i, e in enumerate(best().get('-'.join(tags), best().get(tags[0], [])))}
    found = [(rank.get(name, 10 ** 6), len(row.get('tags', ())), len(name), name) for name, row in events().items()
             if all(t in row.get('tags', ()) for t in tags)]
    found.sort()
    ids = [f[-1] for f in found]
    return ids[:limit] if limit else ids


def original_of(event_id):
    row = event(event_id)
    return row.get('original') if row else None


def all_tags():
    out = {}
    for row in events().values():
        for t in row.get('tags', ()):
            out[t] = out.get(t, 0) + 1
    return out
