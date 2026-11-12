"""`videocraft clips pack <run>`: per short in clips/<n>/, a title, a description, hashtags and a thumbnail frame,
into clips/<n>/meta.json (and clips/<n>/thumbnail.png).

The thumbnail is the frame with a face and big text: sampled every THUMB_STEP frames of the short, each frame is
scored from what the take logged (no model): the biggest complete text on screen (text.json: cap height, a key word
on it), the subject's size in frame and whether it faces the camera (actors.csv head yaw against the camera's yaw),
and the frame's own contrast and brightness (a black frame or a fade never wins). Titles and descriptions come from
the moment (its joke, beat or key line) and the story (premise logline, bible characters); `--ask` has a model write
them instead (agents.ask), from the same facts and the thumbnail.
"""
import json
import re
import statistics
import subprocess
from pathlib import Path

from videocraft import tools
from videocraft.clips import timemap
from videocraft.measure import camera as cam
from videocraft.paths import ROOT

THUMB_STEP = 6
BASE_TAGS = ['#minecraft', '#shorts', '#minecraftanimation']
STOP = {'you', 'the', 'and', 'this', 'that', 'him', 'her', 'its', 'it', 'me', 'my', 'our', 'your', 'win', 'yes', 'no', 'not', 'again'}


def _story(run):
    """(story id, premise text, bible text) of the story a run was made from (or of an assembly's first part)."""
    names = [Path(run).parent.name]
    for name in names + [re.sub(r'-(vertical|v)$', '', n) for n in names]:
        d = ROOT / 'stories' / name
        if (d / 'premise.md').exists():
            bible = (d / 'bible.toml').read_text() if (d / 'bible.toml').exists() else ''
            return name, (d / 'premise.md').read_text(), bible
    return None, '', ''


def logline(premise):
    m = re.search(r'## Logline\s*\n(.+?)(\n## |\Z)', premise, re.S)
    return ' '.join(m.group(1).split()) if m else ''


def characters(bible):
    """Names of the bible's characters, in order, once each."""
    names = re.findall(r'^name\s*=\s*"([^"]+)"', bible, re.M)
    return list(dict.fromkeys(names))


def hashtags(names, keys, limit=8):
    tags = list(BASE_TAGS)
    for word in names + keys:
        tag = '#' + re.sub(r'[^a-z0-9]', '', word.lower())
        if len(tag) > 3 and tag[1:] not in STOP and tag not in tags:
            tags.append(tag)
    return tags[:limit]


def frame_score(texts, subjects, luma, contrast):
    """A thumbnail score for one frame. texts: [(cap height px, has key word)] of complete text on screen; subjects:
    [(height fraction, facing camera)]; luma 0-255 mean, contrast its standard deviation."""
    if luma < 28:
        return -10.0, 'too dark'
    why, score = [], 0.0
    if texts:
        cap, key = max(texts)[:2]
        score += min(2.0, cap / 60.0) + (0.7 if key else 0.0)
        why.append(f'text {cap:.0f} px' + (' with a key word' if key else ''))
    if subjects:
        h, facing = max(subjects)
        score += min(2.0, h / 0.25) + (1.0 if facing else 0.0)
        why.append(f'subject {h:.0%} of the height' + (', facing the camera' if facing else ''))
    score += min(1.0, contrast / 60.0)
    return round(score, 3), ', '.join(why) or 'contrast only'


def _gray_samples(video, frames, step, w=36, h=64):
    """(mean luma, contrast) of every `step`-th frame of a video (tiny grey frames from ffmpeg)."""
    out = subprocess.run([tools.ffmpeg(), '-v', 'error', '-i', str(video), '-vf', f"select='not(mod(n\\,{step}))',scale={w}:{h},format=gray",
                          '-fps_mode', 'passthrough', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    size = w * h
    stats = []
    for i in range(0, len(out) - size + 1, size):
        px = out[i:i + size]
        stats.append((sum(px) / size, statistics.pstdev(px)))
    return stats


def _short_map(clip):
    """(map, master frame offset) that says what each frame of the short shows: the vertical take's own timeline
    when re-shot, else the source run's master from the range start."""
    from videocraft import store
    if clip.get('reshoot'):
        return timemap.load(store.Iteration(Path(clip['reshoot']))), 0
    return timemap.load(store.Iteration(Path(clip['run']))), int(round(clip['start'] * clip['fps']))


def thumbnail(clip, folder):
    m, offset = _short_map(clip)
    video = Path(clip['video'])
    samples = _gray_samples(video, clip['frames'], THUMB_STEP)
    texts_of, actors_of, frames_of = {}, {}, {}
    best = None
    for j, (luma, contrast) in enumerate(samples):
        k = j * THUMB_STEP
        seg, src = m.locate(offset + k)
        texts, subjects = [], []
        if seg is not None and src is not None and seg.run:
            key = (seg.run, seg.shot)
            d = timemap.shot_dir(seg)
            if key not in texts_of:
                texts_of[key] = (timemap._json(d / 'text.json') or {}).get('items', [])
                actors_of[key] = cam.read_csv(d / 'actors.csv') if (d / 'actors.csv').exists() else []
                frames_of[key] = {int(r['frame']): r for r in cam.read_csv(d / 'frames.csv')} if (d / 'frames.csv').exists() else {}
            for item in texts_of[key]:
                shown = item.get('shown_frame') if item.get('shown_frame') is not None else item.get('first_frame')
                if shown is not None and item.get('last_frame') is not None and shown <= src <= item['last_frame'] and item.get('cap_height'):
                    texts.append((float(item['cap_height']), any(w.get('key') for w in item.get('words') or []), str(item.get('text') or '')))
            row = frames_of[key].get(src)
            if row and actors_of[key]:
                for a in actors_of[key]:
                    if int(a['frame']) != src:
                        continue
                    track = cam.subject_track([row], [a], str(a['actor']), 1.3)
                    v = track[0][1] if track else None
                    if v and 0 <= v[0] <= 1 and 0 <= v[1] <= 1:
                        head = a.get('head_yaw') if isinstance(a.get('head_yaw'), float) else a.get('yaw')
                        facing = isinstance(head, float) and abs(((head - (row['cam_yaw'] + 180)) + 180) % 360 - 180) < 50
                        subjects.append((v[2], facing))
        score, why = frame_score(texts, subjects, luma, contrast)
        if best is None or score > best[0]:
            best = (score, k, why, max(texts)[2] if texts else '')
    score, k, why, text = best or (0, 0, 'first frame', '')
    out = Path(folder) / 'thumbnail.png'
    subprocess.run([tools.ffmpeg(), '-y', '-v', 'error', '-i', str(video), '-vf', f"select='eq(n\\,{k})'", '-fps_mode', 'passthrough',
                    '-frames:v', '1', str(out)], check=True)
    return {'file': out.name, 'frame': k, 't': k / clip['fps'], 'score': score, 'why': why, 'text': text}


def _lines(clip):
    """The words spoken or captioned inside the short, as lines of text, and its key words."""
    from videocraft import store
    m = timemap.load(store.Iteration(Path(clip['run'])))
    words = [w for w in timemap.words(m) if clip['start'] - 1e-6 <= w.start < clip['end']]
    lines = {}
    for w in words:
        lines.setdefault(w.line, []).append(w.text)
    return [' '.join(ws) for ws in lines.values()], [w.text.strip('.,!?') for w in words if w.key]


def describe(clip, story, premise, bible, thumb_text=''):
    mo = clip.get('moment') or {}
    lines, keys = _lines(clip)
    names = characters(bible)
    title = (mo.get('title') or thumb_text or (lines[-1] if lines else '') or (story or 'Minecraft short').replace('-', ' ')).strip()
    title = re.sub(r'\s+', ' ', title.replace('*', ''))
    if len(title) > 60:
        title = title[:57].rsplit(' ', 1)[0] + '...'
    parts = []
    if lines:
        quote = max(lines, key=len)
        parts.append(f'"{quote}"')
    if logline(premise):
        parts.append(logline(premise))
    parts.append('Filmed entirely inside Minecraft.')
    return {'title': title, 'description': ' '.join(parts), 'hashtags': hashtags(names, keys)}


def ask_copy(meta, clip, premise, model, say):
    from videocraft import agents
    if not agents.backend():
        say('  --ask: no model; the titles are from the moments')
        return meta
    lines, _ = _lines(clip)
    prompt = ('Write the upload copy for a vertical Minecraft comedy short. You see one still (the thumbnail) and text, not '
              'the video.\n\n' + (f'The story:\n{logline(premise)}\n\n' if premise else '')
              + f'The moment: {(clip.get("moment") or {}).get("title", "")}\nLines in it:\n' + '\n'.join(lines)
              + f'\n\nCurrent draft: {json.dumps(meta)}\n\nAnswer JSON: {{"title" (at most 60 characters, no clickbait '
                'lies), "description" (one or two sentences), "hashtags" (at most 8, starting #minecraft #shorts)}}.')
    schema = {'type': 'object', 'properties': {'title': {'type': 'string'}, 'description': {'type': 'string'},
                                               'hashtags': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['title', 'description']}
    try:
        from videocraft.review.reviews import extract_json
        answer = extract_json(agents.ask(prompt, images=[Path(clip['folder']) / meta['thumbnail']['file']], schema=schema, model=model, timeout=900))
    except Exception as e:
        say(f'  --ask failed ({type(e).__name__}: {e}); keeping the draft')
        return meta
    meta.update({k: answer[k] for k in ('title', 'description', 'hashtags') if answer.get(k)})
    meta['copy_by'] = agents.model_name(model)
    return meta


def pack(it, ask=False, model=None, say=print):
    base = it.path / 'clips'
    out = []
    for f in sorted(base.glob('*/clip.json'), key=lambda p: (not p.parent.name.isdigit(), p.parent.name.zfill(6))):
        clip = json.loads(f.read_text())
        if not Path(clip['video']).exists():
            continue
        story, premise, bible = _story(clip['run'])
        thumb = thumbnail(clip, f.parent)
        meta = {'clip': f.parent.name, 'video': Path(clip['video']).name, 'seconds': clip['seconds'], 'method': clip['method'],
                'range': [clip['start'], clip['end']], 'story': story, **describe(clip, story, premise, bible, thumb['text']),
                'thumbnail': thumb, 'copy_by': 'heuristic'}
        if ask:
            meta = ask_copy(meta, clip, premise, model, say)
        (f.parent / 'meta.json').write_text(json.dumps(meta, indent=2) + '\n')
        out.append(meta)
    return out
