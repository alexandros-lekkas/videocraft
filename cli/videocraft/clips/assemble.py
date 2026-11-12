"""Long form: several finished runs (episodes, scenes) joined into one video with chapter cards between them.

    assemble(parts, name, cards='game', ...) -> the assembly iteration (runs/<name>/<NNNN>/, kind "assembly")

What it writes (cut/):
    master.mp4       every part in order, a chapter card before each; H.264 + AAC, mp4 chapters from chapters.ffmeta
    timeline.json    fps, size, frames, `parts` [{index, kind: card | part, title, run, out_start, out_frames}] and
                     `clips`: every part's own timeline clips shifted into assembly frames, each with its `run` and
                     `part`, so measure and `clips` map any frame back to its source run and shot (clips/timemap.py)
    chapters.txt     YouTube's description format (0:00 Title)
    chapters.ffmeta  ffmpeg's FFMETADATA1 chapters (also muxed into master.mp4)
    audio.wav        the whole mix re-mastered to -14 LUFS integrated, true peak -1 dBTP; each part first levelled to
                     -14 on its own so a quiet episode does not stay quiet
    assembly.json    parts, per-part loudness before and after, chapter problems YouTube would refuse, timings

Chapter cards (`cards`): `game` renders them in the game, one shot per chapter of a small card script, taken once and
reused while the titles and size are the same (runs/chapter-cards/); `plain` draws them with the bitmap font (no
take); `none` joins the parts back to back.
"""
import json
import subprocess
import time
from pathlib import Path

from videocraft import tools
from videocraft.audio import dsp, loudness
from videocraft.clips import chapters as chapters_
from videocraft.clips import runs
from videocraft.measure import probe

CARD_SECONDS = 2.5
CARD_PROJECT = 'chapter-cards'
SR = dsp.SR


def _toml(s):
    return json.dumps(str(s), ensure_ascii=False)


def card_script(titles, width, height, fps, seconds=CARD_SECONDS, label='Part'):
    """A shot script with one full-frame card shot per chapter: the title drops in, the part number under it."""
    lines = ['# Chapter cards for `videocraft assemble` (written by cli/videocraft/clips/assemble.py).',
             f'name = "{CARD_PROJECT}"', 'seed = 1', '', '[output]', f'width = {width}', f'height = {height}', f'fps = {fps}', '',
             '[world]', 'seed = "videocraft"', 'time = 6000', '', '[edit]', 'audio = "none"', '']
    for n, title in enumerate(titles, 1):
        lines += ['[[shot]]', f'name = "card-{n}"', f'duration = {seconds}',
                  'camera = { rig = "orbit", center = { anchor = "spawn" }, radius = 12, height = 30, sweep = 5 }', '',
                  '[[shot.cue]]', 'at = 0.0', 'do = "card"', f'title = {_toml(title)}', f'subtitle = {_toml(f"{label} {n}")}',
                  'style = "drop"', '']
    return '\n'.join(lines)


def game_cards(titles, width, height, fps, seconds, workdir, say=print, label='Part'):
    """[(video path, frames)] of in-game cards: a cached take when one with the same script passed, else a new take."""
    text = card_script(titles, width, height, fps, seconds, label)
    it = runs.reuse(CARD_PROJECT, text)
    if it:
        say(f'  chapter cards: reusing {it.path}')
    else:
        path = Path(workdir) / 'cards.toml'
        path.write_text(text)
        say(f'  chapter cards: one take of {len(titles)} card(s) at {width}x{height}')
        it, code = runs.take(path, say=say, cut=False)
        if code != 0:
            raise SystemExit(f'the chapter card take failed (exit {code}); see {it.take / "game.log" if it else path}; try --cards plain')
    frames = {s['name']: s['frames'] for s in it.result()['shots']}
    return [(it.take / 'shots' / f'card-{n}' / 'video.mp4', frames[f'card-{n}']) for n in range(1, len(titles) + 1)], str(it.path)


def plain_card(path, title, sub, width, height):
    """A black card PNG with the title and the part number in the bitmap font (no take)."""
    from videocraft.review.image import Canvas, text_width
    c = Canvas(width, height)
    short = min(width, height)
    big = max(4, int(short / 1080 * 12))
    small = max(2, big // 2)
    words = title.upper()
    while text_width(words, big) > width * 0.9 and big > 2:
        big -= 1
    y = height // 2 - 7 * big
    c.text((width - text_width(words, big)) // 2, y, words, big, (255, 255, 255))
    c.text((width - text_width(sub.upper(), small)) // 2, y + 7 * big + 3 * small, sub.upper(), small, (201, 209, 220))
    c.png(path)
    return path


def _pcm(path, seconds, has_audio, gain_db=0.0):
    """The part's audio as 48 kHz stereo float32 bytes, exactly `seconds` long (silence where it has none), with a gain."""
    n = int(round(seconds * SR)) * 2 * 4
    if not has_audio:
        return bytes(n)
    out = subprocess.run([tools.ffmpeg(), '-v', 'error', '-i', str(path), '-vn', '-af', f'volume={gain_db:.3f}dB,apad', '-t', f'{seconds:.6f}',
                          '-ac', '2', '-ar', str(SR), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
    return out[:n] + bytes(max(0, n - len(out)))


def level_gain(measured, target=loudness.TARGET, true_peak=None, ceiling=loudness.CEILING, most=12.0):
    """dB to bring a part to `target` LUFS: at most `most` dB up (a near-silent part stays quiet rather than hiss),
    and the master's limiter takes care of peaks."""
    if measured is None or measured < -69:
        return 0.0
    return max(-most, min(most, target - measured))


def assemble(parts, name, cards='game', card_seconds=CARD_SECONDS, cold_open=False, label='Part', measure_it=True, say=print):
    """parts: [(iteration, title)]. Returns the assembly iteration."""
    if not parts:
        raise SystemExit('assemble needs at least one part')
    started = time.time()
    ffmpeg = tools.ffmpeg()
    infos = []
    for it, title in parts:
        master = runs.master_of(it)
        if not master:
            raise SystemExit(f'{it.path} has no cut/master.mp4; cut it first (videocraft cut {it.path})')
        infos.append({'it': it, 'title': title, 'master': master, **probe(master)})
    width, height, fps = infos[0]['width'], infos[0]['height'], int(round(infos[0]['fps']))
    out = runs.new_iteration(name, 'assembly', {'parts': [str(i['it'].path) for i in infos], 'cards': cards})
    say(f'videocraft assemble: {name} iteration {out.name}, {len(infos)} part(s), {width}x{height} {fps} fps, cards {cards}')

    titles = [i['title'] for i in infos]
    card_files, card_run = [], None
    if cards == 'game':
        card_files, card_run = game_cards(titles, width, height, fps, card_seconds, out.path, say, label)
    elif cards == 'plain':
        n = int(round(card_seconds * fps))
        for k, title in enumerate(titles, 1):
            png = plain_card(out.cut / f'card-{k}.png', title, f'{label} {k}', width, height)
            card_files.append((png, n))
    elif cards != 'none':
        raise SystemExit(f'--cards is game, plain or none (got {cards})')

    # The order: card, part, card, part, ... (no card before the first part with cold_open).
    pieces = []
    for k, info in enumerate(infos):
        if card_files and not (cold_open and k == 0):
            path, n = card_files[k]
            pieces.append({'kind': 'card', 'title': info['title'], 'path': path, 'frames': n, 'still': str(path).endswith('.png'),
                           'audio': False, 'run': card_run, 'part_of': k})
        n = int(round(info['seconds'] * fps)) if abs(info['fps'] - fps) > 0.01 else info['frames']
        pieces.append({'kind': 'part', 'title': info['title'], 'path': info['master'], 'frames': n, 'still': False,
                       'audio': info['audio'], 'run': str(info['it'].path), 'part_of': k, 'info': info})

    # Picture: every piece scaled into the frame, at the assembly rate, trimmed to its frame count, joined.
    args, graph, labels = [], [], []
    for j, p in enumerate(pieces):
        if p['still']:
            args += ['-loop', '1', '-framerate', str(fps), '-i', str(p['path'])]
        else:
            args += ['-i', str(p['path'])]
        graph.append(f'[{j}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,'
                     f'fps={fps},trim=end_frame={p["frames"]},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v{j}]')
        labels.append(f'[v{j}]')
    graph.append(''.join(labels) + f'concat=n={len(labels)}:v=1:a=0,setpts=N/({fps}*TB)[v]')
    picture = out.cut / 'picture.mp4'
    (out.cut / 'graph.txt').write_text(';\n'.join(graph) + '\n')
    say('  picture: joining ' + ', '.join(f'{p["kind"]} {p["frames"]}f' for p in pieces))
    subprocess.run([ffmpeg, '-y', '-loglevel', 'error', *args, '-filter_complex', ';'.join(graph), '-map', '[v]', '-r', str(fps),
                    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
                    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-an', str(picture)], check=True)

    # Timeline and chapters.
    at, parts_out, clips, chapter_list = 0, [], [], []
    for j, p in enumerate(pieces):
        entry = {'index': j, 'kind': p['kind'], 'title': p['title'], 'run': p['run'], 'out_start': at, 'out_frames': p['frames'], 'part': p['part_of']}
        parts_out.append(entry)
        if p['kind'] == 'part':
            tfile = Path(p['run']) / 'cut' / 'timeline.json'
            data = json.loads(tfile.read_text()) if tfile.exists() else {'fps': fps, 'clips': [{'kind': 'shot', 'shot': None, 'out_start': 0, 'out_frames': p['frames']}]}
            k = fps / int(data.get('fps') or fps)
            for c in data.get('clips', []):
                c = dict(c)
                c['out_start'] = at + int(round(int(c['out_start']) * k))
                c['out_frames'] = int(round(int(c['out_frames']) * k))
                if k != 1:
                    c.pop('src_map', None)
                c['run'], c['part'] = p['run'], p['part_of']
                clips.append(c)
        else:
            clips.append({'index': len(clips), 'kind': 'card', 'shot': None, 'out_start': at, 'out_frames': p['frames'],
                          'run': p['run'], 'part': p['part_of'], 'title': p['title']})
        at += p['frames']
    total = at
    for j, p in enumerate(parts_out):    # a chapter starts on its card (or on the part when it has none)
        if p['kind'] == 'card' or not (j and parts_out[j - 1]['kind'] == 'card' and parts_out[j - 1]['part'] == p['part']):
            chapter_list.append({'title': p['title'], 'start': p['out_start'] / fps, 'part': p['part']})
    for a, b in zip(chapter_list, chapter_list[1:]):
        a['end'] = b['start']
    chapter_list[-1]['end'] = total / fps
    timeline = {'fps': fps, 'width': width, 'height': height, 'frames': total, 'parts': parts_out, 'clips': clips,
                'chapters': chapter_list,
                'conventions': 'assembly frames; each clip keeps its own run\'s src_* frames; `run` is the source iteration'}
    (out.cut / 'timeline.json').write_text(json.dumps(timeline, indent=1) + '\n')
    (out.cut / 'chapters.txt').write_text(chapters_.youtube(chapter_list))
    ffmeta = out.cut / 'chapters.ffmeta'
    ffmeta.write_text(chapters_.ffmetadata(chapter_list, title=name))

    # Sound: each part levelled to -14 on its own, cards silent, then the whole mastered to -14 / -1 dBTP.
    raw = out.cut / 'mix.f32'
    levels = []
    with open(raw, 'wb') as fh:
        for p in pieces:
            row, gain = {'title': p['title'], 'kind': p['kind']}, 0.0
            if p['audio']:
                before = loudness.measure(p['path'])
                gain = level_gain(before['integrated'])
                row.update(before=before['integrated'], gain_db=round(gain, 2))
            levels.append(row)
            fh.write(_pcm(p['path'], p['frames'] / fps, p['audio'], gain))
    wav = out.cut / 'audio.wav'
    mastered = loudness.master(raw, wav)
    raw.unlink()
    master = out.cut / 'master.mp4'
    subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-i', str(picture), '-i', str(wav), '-i', str(ffmeta),
                    '-map', '0:v', '-map', '1:a', '-map_metadata', '2', '-map_chapters', '2', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
                    '-t', f'{total / fps:.6f}', '-movflags', '+faststart', str(master)], check=True)
    picture.unlink()
    for row, p in zip(levels, parts_out):    # each part's loudness inside the finished master
        if row['kind'] == 'part' and row.get('before') is not None:
            row['after'] = loudness.measure(wav, start=p['out_start'] / fps, duration=p['out_frames'] / fps)['integrated']
    subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-ss', f'{max(0.0, total / fps / 2):.3f}', '-i', str(master), '-frames:v', '1',
                    str(out.cut / 'poster.png')], check=True)
    problems = chapters_.problems(chapter_list, total / fps)
    record = {'name': name, 'iteration': out.name, 'width': width, 'height': height, 'fps': fps, 'frames': total, 'seconds': total / fps,
              'cards': cards, 'card_run': card_run, 'parts': parts_out, 'chapters': chapter_list, 'chapter_problems': problems,
              'loudness': {'master': mastered, 'parts': levels}, 'seconds_taken': round(time.time() - started, 1)}
    (out.cut / 'assembly.json').write_text(json.dumps(record, indent=2) + '\n')
    (out.path / 'plan.json').write_text(json.dumps({'version': 1, 'name': name, 'kind': 'assembly',
                                                   'output': {'width': width, 'height': height, 'fps': fps}, 'shots': []}, indent=2) + '\n')
    (out.path / 'edit.json').write_text(json.dumps({'kind': 'assembly', 'clip': []}, indent=2) + '\n')
    if measure_it:
        from videocraft.measure import measure_video
        measure_video(master, out=out.measure)
    from videocraft import store
    store.update_index(out.path.parent)
    return out, record
