"""The trailer's own takes: footage the finished runs do not have, filmed by videocraft itself.

    python3 trailer/footage.py [names...]       write runs/trailer/footage/<name>.toml and run each one

Two kinds, both listed in trailer.toml under [footage.take]:
  - a script of its own (trailer/footage/keynote.toml), run as it is;
  - an example with in-game captions added (`from = "examples/rigs.toml"` and one `[[...caption]]` per shot): the
    example is copied with a caption cue appended to each named shot, so every clip in the trailer carries the
    game's own caption style (Minecraft's font, the key word in yellow, the speaker tag). Skin paths are made
    absolute because the copy lives in runs/.
Every run prints its RESULT lines; they land in runs/trailer/footage/<name>.txt.
"""
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'runs' / 'trailer' / 'footage'


def toml_str(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def caption_cue(c):
    lines = ['', '[[shot.cue]]', f'at = {float(c.get("at", 0.3))}', 'do = "caption"', f'text = {toml_str(c["text"])}']
    if c.get('speaker'):
        lines.append(f'speaker = {{ name = {toml_str(c["speaker"])}, color = {toml_str(c.get("color", "#a8c8ff"))} }}')
    if c.get('position'):
        lines.append(f'position = {toml_str(c["position"])}')
    return '\n'.join(lines) + '\n'


def derive(src, name, captions):
    """`src` with `name` as its script name and each caption appended to its shot's cues."""
    text = (ROOT / src).read_text(encoding='utf-8')
    skins = (ROOT / src).parent / 'skins'
    text = re.sub(r'^(\s*skin\s*=\s*")skins/', lambda m: m.group(1) + str(skins) + '/', text, flags=re.M)
    text = re.sub(r'^name\s*=\s*"[^"]*"', f'name = {toml_str(name)}', text, count=1, flags=re.M)
    parts = re.split(r'(?m)^(?=\[\[shot\]\]\s*$)', text)
    by_shot = {}
    for c in captions:
        by_shot.setdefault(c['shot'], []).append(c)
    out = [parts[0]]
    for block in parts[1:]:
        m = re.search(r'(?m)^name\s*=\s*"([^"]+)"', block)
        shot = m.group(1) if m else None
        cues = ''.join(caption_cue(c) for c in by_shot.pop(shot, []))
        # Insert before the first top-level table that is not part of the shot ([edit], [[edit.clip]] …).
        tail = re.search(r'(?m)^\[(?!\[?shot[\].])', block)
        cut = tail.start() if tail else len(block)
        out.append(block[:cut].rstrip('\n') + '\n' + cues + '\n' + block[cut:])
    if by_shot:
        raise SystemExit(f'footage {name}: no shot named {", ".join(by_shot)} in {src}')
    return ''.join(out)


def main(argv):
    spec = tomllib.loads((ROOT / 'trailer' / 'trailer.toml').read_text(encoding='utf-8'))
    takes = spec['footage']['take']
    names = argv or [t['name'] for t in takes]
    OUT.mkdir(parents=True, exist_ok=True)
    code = 0
    for t in takes:
        if t['name'] not in names:
            continue
        if 'script' in t:
            script = ROOT / t['script']
        else:
            script = OUT / f'{t["name"]}.toml'
            script.write_text(derive(t['from'], t['run'], t.get('caption', [])), encoding='utf-8')
        log = OUT / f'{t["name"]}.txt'
        print(f'footage  {t["name"]}: bin/videocraft run {script.relative_to(ROOT)}', flush=True)
        p = subprocess.run([str(ROOT / 'bin' / 'videocraft'), 'run', str(script), *t.get('args', [])],
                           cwd=ROOT, capture_output=True, text=True)
        log.write_text(p.stdout + p.stderr, encoding='utf-8')
        for line in (p.stdout + p.stderr).splitlines():
            if line.split(' ', 1)[0] in ('RESULT', 'VIDEO', 'TIME'):
                print('  ' + line)
        code = code or p.returncode
    return code


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
