"""`videocraft audio …`: the sound track of an iteration, the synth bed on its own, and what was logged and placed.

  videocraft audio mix <iteration> [--original] [--mux]     cut/audio.wav + cut/audio.json (and into cut/master.mp4)
  videocraft audio synth -o bed.wav [--style S] [--seconds N] [--bpm B] [--key K] [--seed N] [--stems]
  videocraft audio events <iteration> [--onsets]            every logged sound: frame, cut time, gain, or why skipped
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

