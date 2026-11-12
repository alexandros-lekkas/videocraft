#!/usr/bin/env python3
"""Fresh reviewers for the trailer: a packet of stills, then one `claude -p` reviewer per role (trailer/rubric.toml)
through videocraft.agents.ask, and a score.

    python3 trailer/review.py [--round N] [--roles design,motion,story]

The packet (runs/trailer/review/<round>/packet/): a contact sheet of each cut (one frame a second for the 16:9, one
every two seconds for the 9:16), strips of consecutive frames (every 3rd frame, 0.05 s apart) at each section's
entrance, and facts.md (timecodes, sections, loudness, where the data on screen came from). Reviews land in
runs/trailer/review/<round>/<role>.json and score.json. Reviewers see stills only and say so.
"""
import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = ROOT / 'runs' / 'trailer'
sys.path.insert(0, str(ROOT / 'cli'))

from videocraft import agents, tools  # noqa: E402
from videocraft.audio import loudness  # noqa: E402


def frames_png(video, times, size, cols, out, label=True):
    """A grid of the frames nearest `times` (seconds), each labelled with its timecode (ffmpeg's own select)."""
    fps = 60
    sel = '+'.join(f'eq(n,{round(t * fps)})' for t in times)
    rows = -(-len(times) // cols)
    vf = f"select='{sel}',scale={size[0]}:{size[1]},tile={cols}x{rows}:padding=6:color=0x000000"
    subprocess.run([tools.ffmpeg(), '-v', 'error', '-y', '-i', str(video), '-vf', vf, '-fps_mode', 'passthrough',
                    '-frames:v', '1', str(out)], check=True)
    return out


def build(round_dir, spec):
    pk = round_dir / 'packet'
    pk.mkdir(parents=True, exist_ok=True)
    h = OUT / spec['exports']['h']
    v = OUT / spec['exports']['v']
    secs = spec['seconds']
    images = []
    images.append(frames_png(h, [i + 0.5 for i in range(int(secs))], (384, 216), 10, pk / '01-contact-16x9.png'))
    if v.exists():
        images.append(frames_png(v, [i + 1.0 for i in range(0, int(secs), 2)], (216, 384), 12, pk / '02-contact-9x16.png'))
    starts = sorted({sc['from'] for sc in spec['scene']} | {c['at'] for sc in spec['scene'] for c in sc.get('clips', [])})
    entrances = [0.6, 3.5, 4.6, 7.8] + [s for s in starts if s > 8] + [33.0, 59.0]
    for i, t0 in enumerate(sorted(set(entrances))):
        times = [max(0.0, t0 - 0.15) + k * 0.05 for k in range(16)]
        images.append(frames_png(h, times, (480, 270), 4, pk / f'1{i:02d}-strip-16x9-{t0:05.2f}s.png'))
    for i, t0 in enumerate([5.0, 16.0, 28.0, 35.0, 42.0, 50.0, 60.0]):
        if v.exists():
            times = [t0 + k * 0.1 for k in range(12)]
            images.append(frames_png(v, times, (216, 384), 12, pk / f'2{i:02d}-strip-9x16-{t0:05.2f}s.png'))
    m = loudness.measure(h)
    facts = [
        '# Facts about the trailer', '',
        f'- 16:9 master: 1920x1080, 60 fps, {secs:.1f} s; 9:16 cut: 1080x1920 (a separate layout, not a crop).',
        f'- Sound (you cannot hear it): an original synthesized bed at 120 bpm (a bar is 2 s; sections start on bars, '
        f'cuts on beats), original library effects (typing, whooshes, pops, a chime), a real voice line in the voice '
        f'section, and the finished film\'s own original-audio track while it plays. Master {m["integrated"]:.1f} LUFS, true peak {m["true_peak"]:.1f} dBTP.',
        '- Everything on screen is real: the terminal output was captured from the commands shown, the hashes are the '
        'framemd5 of two takes, the scores are from the benchmark film\'s review rounds; the footage was filmed by '
        'videocraft (in-game captions are the game\'s own text layer, by design: the owner wants that caption style).',
        '', '## Sections (16:9 timecodes)', '']
    for sc in spec['scene']:
        facts.append(f'- {sc["from"]:5.1f}-{sc["to"]:5.1f} s  {sc["type"]}' +
                     (f': {sc.get("header", "")}' if sc.get('header') else ''))
    facts += ['', '## Images', '',
              '- 01: one frame per second, 0.5 s, 1.5 s, … (read left to right, ten a row).',
              '- 02: the 9:16 cut, one frame every 2 s from 1 s.',
              '- 1xx: 16 consecutive frames 0.05 s apart (every 3rd frame) around a section or clip entrance; the file '
              'name is the start time.',
              '- 2xx: the 9:16 cut, 12 frames 0.1 s apart from the time in the name.']
    (pk / 'facts.md').write_text('\n'.join(facts) + '\n', encoding='utf-8')
    return images, (pk / 'facts.md').read_text(encoding='utf-8')


SCHEMA = {
    'type': 'object',
    'properties': {
        'scores': {'type': 'object', 'additionalProperties': {'type': 'integer', 'minimum': 1, 'maximum': 10}},
        'limits': {'type': 'string'},
        'notes': {'type': 'array', 'items': {'type': 'object', 'properties': {
            't': {'type': 'string'}, 'text': {'type': 'string'}}, 'required': ['t', 'text']}},
        'fixes': {'type': 'array', 'items': {'type': 'object', 'properties': {
            'fix': {'type': 'string'}, 'why': {'type': 'string'}, 't': {'type': 'string'}}, 'required': ['fix', 'why']}},
    },
    'required': ['scores', 'limits', 'notes', 'fixes'],
}


def prompt_for(role, crits, rubric, facts, brief):
    lines = [
        f'You are a fresh reviewer ({role}) of a 70-second launch trailer for videocraft, an open-source tool that films '
        'videos inside Minecraft from a shot script (a Fabric mod plays the script in a hidden game and captures every '
        'frame; a Python CLI cuts, measures and has reviewer agents score the result).', '',
        f'The brief the trailer was made to: {brief}', '',
        'You see stills only: contact sheets and strips of consecutive frames. You cannot watch the motion or hear the '
        'sound; judge motion from the consecutive frames and say in `limits` what you could not judge.', '',
        'Score each of your criteria 1-10 against its anchors (5 and 9 are described; interpolate; be strict: 8 means '
        'a professional would ship it, 10 is the best you have seen). Then give notes with timecodes and concrete fixes '
        'a motion designer could apply (positions, sizes, timings in seconds), most important first, at most 6.', '',
        '## Your criteria', '']
    for c in crits:
        lines += [f'### {c["id"]}: {c["name"]}', f'Measures: {c["measures"]}', f'5: {c["anchor_5"]}', f'9: {c["anchor_9"]}', '']
    lines += ['## Facts', '', facts, '',
              f'Answer with JSON only: {{"scores": {{{", ".join(json.dumps(c["id"]) + ": n" for c in crits)}}}, '
              '"limits": "...", "notes": [{"t": "0:12", "text": "..."}], "fixes": [{"fix": "...", "why": "...", "t": "0:12"}]}']
    return '\n'.join(lines)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument('--round', type=int, required=True)
    ap.add_argument('--roles', default='design,motion,story')
    args = ap.parse_args(argv)
    spec = tomllib.loads((HERE / 'trailer.toml').read_text(encoding='utf-8'))
    rubric = tomllib.loads((HERE / 'rubric.toml').read_text(encoding='utf-8'))
    rd = OUT / 'review' / f'{args.round:02d}'
    images, facts = build(rd, spec)
    print(f'PACKET   {rd / "packet"} ({len(images)} images)', flush=True)
    brief = ('"a Claude motion-graphicsy trailer showing off the videocraft CLI": calm, premium, editorial motion '
             'design; a deep charcoal canvas, one accent colour, generous whitespace, a crisp sans-serif plus a '
             'monospace for code, smooth eased kinetic typography, a terminal that types real commands and prints real '
             'output, full-bleed cuts to real footage made by the tool; no third-party logos; ends on the videocraft '
             'logo, the repo URL and an unofficial/not-affiliated line. The owner\'s story for it: open on a prompt typed '
             'into a generic, code-drawn agent chat (no real product\'s UI or marks) and the agent\'s real videocraft '
             'output; match-cut into Minecraft and show the agent at work there (a set built block by block, actors '
             'walking to marks, a camera rig flying, a take recording with REC and a frame counter, captions in the '
             'game\'s own style, a voice waveform); then the agent editing (the timeline assembling, cuts snapping to '
             'words, music ducking under lines, reviewer scores, a climb step); the finished film playing; end on the '
             'command line and the repo URL.')
    for role in args.roles.split(','):
        crits = [c for c in rubric['criterion'] if c['role'] == role]
        out = rd / f'{role}.json'
        if out.exists():
            continue
        print(f'REVIEW   {role}: {", ".join(c["id"] for c in crits)} (asking the model)', flush=True)
        text = agents.ask(prompt_for(role, crits, rubric, facts, brief), images=images, schema=SCHEMA, timeout=2400)
        body = text.strip().removeprefix('```json').removesuffix('```').strip()
        data = json.loads(body[body.find('{'):body.rfind('}') + 1])
        data['reviewer'] = role
        out.write_text(json.dumps(data, indent=1), encoding='utf-8')
        print(f'         {data["scores"]}', flush=True)
    scores = {}
    for role in args.roles.split(','):
        f = rd / f'{role}.json'
        if f.exists():
            scores.update(json.loads(f.read_text(encoding='utf-8'))['scores'])
    avg = sum(scores.values()) / max(len(scores), 1)
    (rd / 'score.json').write_text(json.dumps({'criteria': scores, 'average': round(avg, 2),
                                               'minimum': min(scores.values()) if scores else None}, indent=1))
    print(f'SCORE    round {args.round}: average {avg:.2f}, minimum {min(scores.values())}; {scores}')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
