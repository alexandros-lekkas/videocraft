"""`videocraft audio …`: the sound track of an iteration, the synth bed on its own, and what was logged and placed.

  videocraft audio mix <iteration> [--original] [--mux]     cut/audio.wav + cut/audio.json (and into cut/master.mp4)
  videocraft audio synth -o bed.wav [--style S] [--seconds N] [--bpm B] [--key K] [--seed N] [--stems]
  videocraft audio events <iteration> [--onsets]            every logged sound: frame, cut time, gain, or why skipped
  videocraft audio find <words or tag>                      the best matches in the Minecraft catalog, palette, library, music
  videocraft audio play-sheet <tag> [-n N]                  a wav of the candidates one after another, to listen to
  videocraft audio catalog --refresh [--no-music]           rebuild catalog/minecraft.toml and music.toml from local assets
  videocraft audio library [--render]                       the original library (and render it all into the cache)
"""
import json
import subprocess
from pathlib import Path


def say(text=''):
    print(text, flush=True)


def register(sub):
    p = sub.add_parser('audio', help='the sound track: mix, synth bed, logged events')
    asub = p.add_subparsers(dest='audio_command', required=True)
    m = asub.add_parser('mix', help='mix and master an iteration\'s sound track into cut/audio.wav')
    m.add_argument('iteration')
    m.add_argument('--original', action='store_true', help='no game audio: synth bed, synthesized stand-ins, voice')
    m.add_argument('--mux', action='store_true', help='also put the audio into cut/master.mp4 (video stream copied)')
    m.set_defaults(run=cmd_mix)
    s = asub.add_parser('synth', help='render the original chiptune bed to a wav')
    s.add_argument('-o', '--output', required=True)
    s.add_argument('--style', default='upbeat')
    s.add_argument('--seconds', type=float, default=30)
    s.add_argument('--bpm', type=float)
    s.add_argument('--key')
    s.add_argument('--seed', type=int, default=1)
    s.add_argument('--stems', action='store_true', help='also write <output>-melody/-bass/-drums.wav')
    s.set_defaults(run=cmd_synth)
    e = asub.add_parser('events', help='what each shot logged and where the mix placed it')
    e.add_argument('iteration')
    e.add_argument('--original', action='store_true')
    e.add_argument('--onsets', action='store_true', help='measure each event\'s onset in a render and compare (±1 frame)')
    e.set_defaults(run=cmd_events)
    f = asub.add_parser('find', help='search the Minecraft sound catalog, the palette, the original library and the music map')
    f.add_argument('words', nargs='+')
    f.add_argument('-n', type=int, default=10, help='matches per section (10)')
    f.set_defaults(run=cmd_find)
    ps = asub.add_parser('play-sheet', help='write a wav of the candidates for a tag or palette entry, one after another')
    ps.add_argument('tag', nargs='+')
    ps.add_argument('-n', type=int, default=6, help='Minecraft candidates (6), plus the library ones')
    ps.add_argument('-o', '--output', help='the wav (default cache/audio/sheets/<tag>.wav)')
    ps.set_defaults(run=cmd_play_sheet)
    c = asub.add_parser('catalog', help='the committed map of Minecraft sounds and music')
    c.add_argument('--refresh', action='store_true', help='rebuild minecraft.toml and music.toml from the local game assets')
    c.add_argument('--no-music', action='store_true', help='with --refresh: the sound events only (music takes about 3 minutes)')
    c.set_defaults(run=cmd_catalog)
    lib = asub.add_parser('library', help='list the original sound library')
    lib.add_argument('--render', action='store_true', help='render every sound into the cache and print its length and level')
    lib.set_defaults(run=cmd_library)


def cmd_mix(args):
    from videocraft import store, tools
    from videocraft.audio import mix
    it = store.open_iteration(args.iteration)
    out = mix.build(it, original=args.original or None)
    if out is None:
        say('No audio: [edit] audio = "none"')
        return 0
    report = json.loads((it.cut / 'audio.json').read_text())
    lo = report['loudness']
    say(f'AUDIO    {out}')
    say(f'LOUDNESS {lo["integrated"]:.1f} LUFS integrated, true peak {lo["true_peak"]:.1f} dBTP, LRA {lo["lra"]:.1f} LU')
    say(f'EVENTS   {len(report["events"])} placed, {len(report["skipped"])} skipped, {len(report["voice"])} voice; mode {report["mode"]}; '
        f'{report["build_seconds"]:.1f} s')
    for g in report['black_gaps']:
        say(f'GAP      {g["time"]:.2f} s for {g["seconds"]:.2f} s: {g["integrated"]:.1f} LUFS')
    if args.mux:
        master = it.cut / 'master.mp4'
        if not master.exists():
            say(f'No {master} to mux into; run the cut first')
            return 1
        tmp = it.cut / 'master.mux.mp4'
        subprocess.run([tools.ffmpeg(), '-y', '-loglevel', 'error', '-i', str(master), '-i', str(out), '-map', '0:v:0', '-map', '1:a:0',
                        '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', str(tmp)], check=True)
        tmp.replace(master)
        say(f'VIDEO    {master}')
    return 0


def cmd_synth(args):
    from videocraft.audio import dsp, loudness, synth
    bed = synth.render(args.seconds, style=args.style, bpm=args.bpm, key=args.key, seed=args.seed)
    out = Path(args.output)
    targets = [(out, synth.mixdown(bed))]
    if args.stems:
        targets += [(out.with_name(f'{out.stem}-{k}{out.suffix}'), v) for k, v in bed.stems.items()]
    for path, buf in targets:
        raw = path.with_suffix('.f32')
        dsp.write_f32(raw, buf, buf)
        lo = loudness.master(raw, path, target=-16)
        raw.unlink()
        say(f'{path}  {bed.style} {bed.bpm:g} bpm key {bed.key}  {lo["integrated"]:.1f} LUFS, true peak {lo["true_peak"]:.1f} dBTP')
    return 0


def cmd_events(args):
    from videocraft import store
    from videocraft.audio import dsp, mix, onsets
    from videocraft.audio import timeline as tl
    it = store.open_iteration(args.iteration)
    edit = it.edit()
    mode = mix._mode(edit, args.original or None)
    timeline = tl.load(it)
    sounds = mix.Sounds('original' if mode == 'original' else 'game')
    mixcfg = edit.get('mix') or {}
    placed, skipped = mix.place_sfx(it, timeline, sounds, mixcfg.get('duck') or (), mixcfg.get('lift'))
    say(f'{"time":>8}  {"shot":12} {"frame":>6}  {"gain":>6} {"pan":>5} {"rate":>5}  {"source":8} event / file')
    for p in placed:
        say(f'{p.time:8.3f}  {p.shot:12} {p.frame:6d}  {dsp.db(p.gain):6.1f} {p.pan:5.2f} {p.rate:5.2f}  {p.source:8} {p.event}  {p.file}')
    for s in skipped:
        say(f'{"-":>8}  {s["shot"]:12} {s["frame"]:6d}  skipped: {s["reason"]}  {s["event"]}')
    if not args.onsets:
        return 0
    n = dsp.seconds_to_samples(timeline.seconds)
    left, right = mix.render_sfx(placed, sounds, n)
    mono = [0.5 * (a + b) for a, b in zip(left, right)]
    rows = onsets.check(placed, mono, timeline.fps)
    say('')
    say(f'ONSETS (effects bus, tolerance ±1 frame = {1000 / timeline.fps:.1f} ms)')
    say(f'{"planned":>9} {"measured":>9} {"error ms":>9}  event')
    bad = 0
    for p, onset, err, ok in rows:
        bad += not ok
        say(f'{p.time:9.4f} {onset if onset is not None else float("nan"):9.4f} {err if err is not None else float("nan"):9.2f}  '
            f'{"ok  " if ok else "MISS"} {p.event}')
    # The master against the mix it was made from: the limiter must not move anything in time.
    out = mix.build(it, original=args.original or None, keep_raw=True)
    raw = it.cut / '.audio-mix.f32'
    if out is not None and raw.exists():
        rl, rr = dsp.read_f32(raw, 2)
        raw.unlink()
        ml, mr = dsp.read_wav16(out)
        shift = onsets.lag([0.5 * (a + b) for a, b in zip(rl, rr)], [0.5 * (a + b) for a, b in zip(ml, mr)])
        say(f'MASTER   delay against the unmastered mix: {shift} samples ({shift / dsp.SR * 1000:.2f} ms)')
        bad += abs(shift) > dsp.SR / timeline.fps
    say(f'RESULT   {"PASS" if not bad else "FAIL"} {sum(ok for *_, ok in rows)}/{len(rows)} onsets within ±1 frame')
    return 0 if not bad else 1



def _words(words):
    from videocraft.audio import catalog
    return catalog.parse_tags(words)


def cmd_find(args):
    from videocraft.audio import catalog, library, synth
    words = _words(args.words)
    query = ' '.join(words)
    say(f'FIND     {query}')
    # The palette: by name or words in its description.
    pal = []
    for name, p in sorted(catalog.palette().items()):
        text = f'{name} {p.get("about", "")}'.lower()
        hits = sum(w in text for w in words)
        if hits:
            pal.append((-hits - (2 if name in ('-'.join(words), query) else 0), name, p))
    pal.sort()
    if pal:
        say('PALETTE  (palette = "<name>"; original: the stand-in in original-only exports)')
        for _, name, p in pal[:args.n]:
            kind = 'pick' if p.get('pick') else 'sequence' if p.get('sequence') else 'roll' if p.get('roll') else 'original only'
            first = (p.get('pick') or p.get('sequence') or [p.get('roll') or {}])[0].get('id', '-')
            say(f'  {name:18} {kind:13} {first:40} original {p.get("original", "-"):18} {p.get("about", "")}')
    # Minecraft events: every tag, else the words in the id.
    ids = catalog.candidates(words)
    how = 'tags'
    if not ids:
        ids = [e for e in catalog.events() if all(w in e for w in words)]
        how = 'words in the id'
    if ids:
        say(f'MINECRAFT ({how}; tag = "{query}" plays the first; your own game install supplies the audio)')
        for e in ids[:args.n]:
            row = catalog.event(e)
            secs = f'{row["seconds"]:.2f} s' if 'seconds' in row else '   -  '
            say(f'  {e:44} {secs:>8} x{row["variants"]:<3} original {row.get("original", "-"):16} {" ".join(row["tags"][:8])}')
        if len(ids) > args.n:
            say(f'  … {len(ids) - args.n} more')
    lib = library.find(words)
    if not lib:
        lib = [(1, n) for n in library.names() if any(w in n or w in library.index()[n].get('about', '') for w in words)]
    if lib:
        say('LIBRARY  (original, made by code: library = "<name>" or source = "original")')
        for _, name in lib[:args.n]:
            entry = library.index()[name]
            say(f'  {name:20} {entry.get("about", ""):60} {" ".join(entry.get("tags", [])[:6])}')
    moods = [w for w in words if w in synth.MOODS]
    tracks = [(f, r) for f, r in catalog.tracks().items() if all(w in f for w in words) or (moods and moods[0] in r.get('mood', ()))]
    if tracks:
        say('MUSIC    ([edit.music] track = "<file>", or mood = "<mood>" to let the mix pick)')
        if moods:
            tracks.sort(key=lambda fr: (fr[1]['mood'].index(moods[0]) if moods[0] in fr[1]['mood'] else 9, fr[0]))
        for f, r in tracks[:args.n]:
            say(f'  {f:46} {r["seconds"]:6.1f} s {r["bpm"]:6.1f} bpm (pulse {r["pulse"]:.2f}) entry {r["entry"]:5.1f} s  {"/".join(r["mood"])}'
                f'{"  vocals" if r.get("vocals") else ""}{"  not a bed" if r.get("bed") is False else ""}')
        if moods:
            style, key = synth.style_for(moods[0])
            say(f'  (original-only: the synth bed in the {style} style{f", {key}" if key else ""})')
    if not (pal or ids or lib or tracks):
        say('Nothing found. Tags look like: pop, plop, ding, boing, whoosh, thud, footstep wood, goat hurt, crowd, sting, fail.')
        return 1
    return 0


def cmd_play_sheet(args):
    """Candidates one after another with 0.4 s of silence between, each levelled like the library; the listing says
    where each starts. Game sounds come from your own install and the wav stays in the git-ignored cache."""
    import wave
    from array import array
    from videocraft.audio import assets, catalog, dsp, library
    from videocraft.paths import ROOT
    words = _words(args.tag)
    name = '-'.join(words)
    items = []
    pal = catalog.palette().get(name)
    ids = catalog.candidates(words, args.n)
    if pal:
        ids = list(dict.fromkeys([s['id'] for s in pal.get('pick', []) + pal.get('sequence', [])] + ids))[:args.n]
    have_assets = assets.available()
    for e in ids:
        if not have_assets:
            break
        files = assets.event_files(e)
        if files:
            items.append((f'minecraft {e} ({files[0]})', assets.decode(files[0], 1)))
    libs = [pal['original']] if pal and pal.get('original') else []
    libs += [n for _, n in library.find(words)[:4] if n not in libs]
    for n in libs:
        items.append((f'library   {n}', library.render(n)))
    if not items:
        say(f'Nothing to play for {name} (videocraft audio find {" ".join(words)})')
        return 1
    gap = dsp.zeros(int(0.4 * dsp.SR))
    out, t, listing = array('f'), 0.0, []
    for label, buf in items:
        g = library.level_gain(buf)
        listing.append((t, len(buf) / dsp.SR, label))
        out.extend(dsp.scaled(buf, g))
        out.extend(gap)
        t = len(out) / dsp.SR
    path = Path(args.output) if args.output else ROOT / 'cache' / 'audio' / 'sheets' / f'{name}.wav'
    path.parent.mkdir(parents=True, exist_ok=True)
    pcm = array('h', [max(-32767, min(32767, int(x * 32767))) for x in out])
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(dsp.SR)
        w.writeframes(pcm.tobytes())
    for start, length, label in listing:
        say(f'{start:7.2f} s  {length:5.2f} s  {label}')
    if not have_assets:
        say('(no game assets here: library sounds only)')
    say(f'SHEET    {path}  ({t:.1f} s)')
    return 0


def cmd_catalog(args):
    from videocraft.audio import catalog
    if not args.refresh:
        say(f'CATALOG  {len(catalog.events())} Minecraft sound events, {len(catalog.palette())} palette entries, '
            f'{len(catalog.tracks())} music tracks (videocraft audio find <words>; --refresh to rebuild from your game assets)')
        return 0
    from videocraft.audio.catalog import build
    build.refresh(music=not args.no_music, say=say)
    catalog.reload()
    return 0


def cmd_library(args):
    from videocraft.audio import dsp, library
    for name in library.names():
        entry = library.index()[name]
        line = f'{name:20} {entry.get("about", ""):64}'
        if args.render:
            buf = library.render(name)
            line += f' {len(buf) / dsp.SR:5.2f} s  rms {dsp.db(dsp.rms(buf)):6.1f} dB'
        say(line + '  ' + ' '.join(entry.get('tags', [])[:5]))
    say(f'LIBRARY  {len(library.names())} original sounds (cli/videocraft/audio/library/)')
    return 0
