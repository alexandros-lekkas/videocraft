"""Chapter markers for a long video: YouTube's description format and ffmpeg's ffmetadata (mp4 chapters).

    youtube(chapters)          '0:00 Title' lines (H:MM:SS past an hour), what YouTube reads from a description
    ffmetadata(chapters, title) the FFMETADATA1 text ffmpeg muxes into the mp4 as chapters (-map_metadata / -map_chapters)
    problems(chapters, total)  what YouTube would refuse: the first not at 0:00, fewer than 3, one under 10 s

A chapter is {title, start, end} in seconds. Pure functions.
"""

YOUTUBE_MIN_CHAPTERS = 3
YOUTUBE_MIN_SECONDS = 10.0


def stamp(seconds):
    """0:00, 1:05, 12:34, 1:02:03: YouTube's timestamps (whole seconds, rounded down so a chapter never starts late)."""
    s = int(max(0.0, seconds) + 1e-6)
    h, rest = divmod(s, 3600)
    m, s = divmod(rest, 60)
    return f'{h}:{m:02d}:{s:02d}' if h else f'{m}:{s:02d}'


def youtube(chapters):
    return ''.join(f'{stamp(c["start"])} {c["title"]}\n' for c in chapters)


def _escape(text):
    out = str(text)
    for ch in ('\\', '=', ';', '#', '\n'):
        out = out.replace(ch, '\\' + ch)
    return out


def ffmetadata(chapters, title=None):
    lines = [';FFMETADATA1']
    if title:
        lines.append(f'title={_escape(title)}')
    for c in chapters:
        lines += ['', '[CHAPTER]', 'TIMEBASE=1/1000', f'START={int(round(c["start"] * 1000))}', f'END={int(round(c["end"] * 1000))}',
                  f'title={_escape(c["title"])}']
    return '\n'.join(lines) + '\n'


def problems(chapters, total=None):
    out = []
    if not chapters:
        return ['no chapters']
    if int(chapters[0]['start'] + 1e-6) != 0:
        out.append(f'the first chapter starts at {stamp(chapters[0]["start"])}, YouTube needs 0:00')
    if len(chapters) < YOUTUBE_MIN_CHAPTERS:
        out.append(f'{len(chapters)} chapter(s); YouTube shows chapters only with at least {YOUTUBE_MIN_CHAPTERS}')
    for c in chapters:
        if c['end'] - c['start'] < YOUTUBE_MIN_SECONDS - 1e-6:
            out.append(f'chapter "{c["title"]}" is {c["end"] - c["start"]:.1f} s; YouTube needs at least {YOUTUBE_MIN_SECONDS:.0f} s')
    for a, b in zip(chapters, chapters[1:]):
        if b['start'] < a['end'] - 1e-6:
            out.append(f'chapter "{b["title"]}" starts before "{a["title"]}" ends')
    if total is not None and chapters[-1]['end'] > total + 0.05:
        out.append(f'the last chapter ends at {chapters[-1]["end"]:.2f} s, after the video ({total:.2f} s)')
    return out


def parse_youtube(text):
    """'0:00 Title' lines back to [(seconds, title)] (for checks and tests)."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        stamp_text, _, title = line.partition(' ')
        parts = [int(p) for p in stamp_text.split(':')]
        seconds = 0
        for p in parts:
            seconds = seconds * 60 + p
        out.append((seconds, title))
    return out
