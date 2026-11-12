"""`videocraft voice`: local text-to-speech per character, word timings, and the say resolver (docs/VOICE.md).

  videocraft voice setup                         the voice venv (cache/voice/venv) and the weights (HF cache)
  videocraft voice doctor                        what is installed, and exactly what is missing
  videocraft voice say [--cast F] --character nibs "text" -o out.wav     out.wav + out.words.json
  videocraft voice script <script.toml> [-o dir] synthesize every say line of a script; the table; <id>.wav files
  videocraft voice check <iteration>             captions, cuts and voice in the master against the word timings
"""
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from videocraft.voice import cast as castmod
from videocraft.voice import front


def say(text=''):
    print(text, flush=True)


def _line(ok, what, detail, required=True):
    mark = 'ok  ' if ok else ('FAIL' if required else 'warn')
    say(f'  {mark}  {what:<16} {detail}')
    return ok or not required


def cmd_doctor(args):
    say('videocraft voice doctor')
    good = True
    apple = sys.platform == 'darwin' and platform.machine() == 'arm64'
    good &= _line(apple, 'apple silicon', f'{sys.platform} {platform.machine()}' + ('' if apple else
                  ': the default engine (Qwen3 on MLX) needs a Mac with Apple silicon; set engine = "kokoro" in the cast (CPU)'), required=False)
    uv = shutil.which('uv')
    _line(bool(uv), 'uv', uv or 'not found: brew install uv (setup uses it to make a Python 3.12 venv)', required=not front.VENV_PY.exists())
    ff = shutil.which('ffmpeg')
    good &= _line(bool(ff), 'ffmpeg', ff or 'not found: brew install ffmpeg')
    esp = shutil.which('espeak-ng')
    good &= _line(bool(esp), 'espeak-ng', esp or 'not found: brew install espeak-ng (Kokoro reads unknown words with it)')
    venv = front.VENV_PY.exists()
    good &= _line(venv, 'voice venv', str(front.VENV_PY) if venv else f'missing {front.VENV}: bin/videocraft voice setup')
    hub = front.hf_hub()
    if venv:
        p = subprocess.run([str(front.VENV_PY), '-I', str(front.WORKER), '--check'], capture_output=True, text=True,
                           env={**os.environ, 'HF_HUB_OFFLINE': '1', 'PYTHONWARNINGS': 'ignore'}, timeout=300)
        info = next((json.loads(l) for l in p.stdout.splitlines() if l.startswith('{')), None)
        if info is None:
            good &= _line(False, 'worker', f'does not start (exit {p.returncode}): {p.stderr.strip().splitlines()[-1:] or ""}; '
                          'bin/videocraft voice setup reinstalls')
        else:
            missing = [k for k, v in info['packages'].items() if v is None]
            good &= _line(not missing, 'packages', ', '.join(f'{k} {v}' for k, v in info['packages'].items() if v) +
                          (f'; missing {", ".join(missing)}: bin/videocraft voice setup' if missing else ''))
    for repo in front.WEIGHTS:
        here = front.weights_cached(repo)
        good &= _line(here, repo.split('/')[-1][:16], f'{hub}' if here else f'not in {hub}: bin/videocraft voice setup downloads it')
    lines = sorted(front.LINES.glob('*.json')) if front.LINES.is_dir() else []
    _line(True, 'line cache', f'{len(lines)} line(s) in {front.LINES}', required=False)
    casts = sorted(castmod.CAST_DIR.glob('*.toml')) if castmod.CAST_DIR.is_dir() else []
    _line(bool(casts), 'casts', ', '.join(c.name for c in casts) or 'none in cast/', required=False)
    mode = os.environ.get('VIDEOCRAFT_VOICE')
    if mode:
        _line(True, 'VIDEOCRAFT_VOICE', mode, required=False)
    say('READY' if good else 'NOT READY: scripts with say cues still compile, with estimated timings and no voice')
    return 0 if good else 1


def cmd_setup(args):
    """uv venv -p 3.12 cache/voice/venv; uv pip install -r requirements.txt; the worker --prefetch (the weights into
    the user's HF cache, 3.8 GB the first time). Every step is printed; a step already done is quick."""
    front.VOICE_DIR.mkdir(parents=True, exist_ok=True)
    uv = shutil.which('uv')
    if not front.VENV_PY.exists():
        if uv:
            steps = [[uv, 'venv', '-p', '3.12', str(front.VENV)]]
        else:
            py = shutil.which('python3.12')
            if not py:
                say('SETUP    needs uv (brew install uv) or a python3.12 on PATH: torch has no wheels for newer Pythons yet')
                return 2
            steps = [[py, '-m', 'venv', str(front.VENV)]]
    else:
        steps = []
    if uv:
        steps.append([uv, 'pip', 'install', '-p', str(front.VENV_PY), '-r', str(front.REQUIREMENTS)])
    else:
        steps.append([str(front.VENV_PY), '-m', 'pip', 'install', '-r', str(front.REQUIREMENTS)])
    if not args.no_weights:
        steps.append([str(front.VENV_PY), '-I', str(front.WORKER), '--prefetch'])
    for cmd in steps:
        say('+ ' + ' '.join(cmd))
        if subprocess.run(cmd).returncode:
            say(f'SETUP    FAIL at: {" ".join(cmd[:3])} (re-run voice setup; downloads resume)')
            return 2
    for tool in ('espeak-ng', 'ffmpeg'):
        if not shutil.which(tool):
            say(f'SETUP    also needed: brew install {tool}')
    say('SETUP    done; bin/videocraft voice doctor')
    return 0


def _cast_for(args, script_path=None):
    raw = {'file': args.cast} if getattr(args, 'cast', None) else {}
    return castmod.load(raw, script_path, log=say)


def cmd_say(args):
    try:
        cast = _cast_for(args)
        ch = cast.character(args.character)
    except castmod.CastError as e:
        say(f'CAST ERROR {e}')
        return 2
    display = args.text.split()
    tokens = [t[1:] if t.startswith('*') and len(t) > 1 else t for t in display]
    mode = 'estimate' if args.estimate else os.environ.get('VIDEOCRAFT_VOICE')
    try:
        engine = front.engine_for(None if mode == 'draft' else mode)
        spec = ch.spec(tokens, args.style, args.speed, cast.styles, draft=args.draft or mode == 'draft')
        r = front.synthesize([spec], engine)[0]
    except front.VoiceError as e:
        say(f'VOICE ERROR {e}')
        return 2
    out = front.copy_line(r, args.out)
    words = ' '.join(f'{w["word"]}@{w["start"]:.2f}' for w in r['words'])
    say(f'LINE     {ch.id} ({spec["engine"]} {spec["voice"]}) {r.get("seconds") or r["words"][-1]["end"]:.2f} s, '
        f'{"cached" if r.get("cached") else r.get("engine")}, timing {r.get("timing")}')
    say(f'WORDS    {words}')
    say(f'WAV      {out if r.get("file") else "(none: estimated timings only)"}')
    say(f'JSON     {out.with_suffix(".words.json")}')
    return 0


def cmd_script(args):
    from videocraft import script as shotscript
    if args.no_voice:
        os.environ['VIDEOCRAFT_VOICE'] = 'estimate'
    try:
        plan, edit = shotscript.compile_script(shotscript.load(args.script), str(args.script))  # runs the resolver
    except shotscript.ScriptError as e:
        say(f'SCRIPT ERROR {e}')
        return 1
    dialogue = edit.get('dialogue', [])
    for s in plan['shots']:
        n = sum(1 for d in dialogue if d['shot'] == s['name'])
        if n:
            say(f'SHOT     {s["name"]:<14} {s["duration"]:.3f} s ({round(s["duration"] * plan["output"]["fps"])} frames), {n} line(s)')
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for d in dialogue:
            front.copy_line({'file': front.ROOT / d['file'] if d.get('file') else None, 'words': d['words']}, out / d['id'])
        (out / 'voice.json').write_text(json.dumps(dialogue, indent=2) + '\n')
        say(f'OUT      {out}')
    return 0


def cmd_check(args):
    from videocraft import store
    from videocraft.voice.check import check
    return 0 if check(store.open_iteration(args.iteration), say)['pass'] else 1


def register(sub):
    p = sub.add_parser('voice', help='local TTS per character, word timings, the say resolver (docs/VOICE.md)', description=__doc__,
                       formatter_class=__import__('argparse').RawDescriptionHelpFormatter)
    vs = p.add_subparsers(dest='voice_command', required=True)
    s = vs.add_parser('setup', help='make cache/voice/venv and download the weights')
    s.add_argument('--no-weights', action='store_true', help='packages only')
    s.set_defaults(run=cmd_setup)
    vs.add_parser('doctor', help='what is installed and what is missing').set_defaults(run=cmd_doctor)
    s = vs.add_parser('say', help='one line: out.wav + out.words.json')
    s.add_argument('text', help='the line; a word starting * is the key word')
    s.add_argument('--character', required=True)
    s.add_argument('--cast', help='a cast file (default: every file in cast/)')
    s.add_argument('--style', help='delivery: shout, whisper, deadpan, excited, ... (docs/VOICE.md)')
    s.add_argument('--speed', type=float, default=1.0)
    s.add_argument('--draft', action='store_true', help="the character's draft voice (Kokoro)")
    s.add_argument('--estimate', action='store_true', help='no synthesis: reading-speed timings')
    s.add_argument('-o', '--out', required=True)
    s.set_defaults(run=cmd_say)
    s = vs.add_parser('script', help="synthesize a shot script's say lines (the cache the compile reads)")
    s.add_argument('script')
    s.add_argument('-o', '--out', help='also copy each line here as <id>.wav + <id>.words.json')
    s.add_argument('--no-voice', action='store_true', help='estimated timings, no synthesis')
    s.set_defaults(run=cmd_script)
    s = vs.add_parser('check', help='measure an iteration: caption words, cut-on cuts, voice in the master')
    s.add_argument('iteration')
    s.set_defaults(run=cmd_check)
