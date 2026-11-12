"""Run-store helpers the clips commands share: resolving parts (iterations, a series), new non-take iterations
(an assembly), taking a script through the normal `run` path, and the window size for a frame size."""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

from videocraft import store
from videocraft.paths import ROOT, RUNS


def master_of(it):
    f = it.cut / 'master.mp4'
    return f if f.exists() else None


def best_iteration(project):
    """The iteration of runs/<project>/ to use as a finished part: index.json's best, else the latest that passed
    and has a master."""
    base = RUNS / project
    index = store.update_index(base) if base.exists() else None
    if index and index.get('best'):
        it = store.Iteration(base / index['best'])
        if master_of(it):
            return it
    for it in reversed(store.iterations(project)):
        if (it.result() or {}).get('verdict') == 'PASS' and master_of(it):
            return it
        if (it.meta() if (it.path / 'meta.json').exists() else {}).get('kind') == 'assembly' and master_of(it):
            return it
    return None


def resolve(ref):
    """An iteration from `<name>`, `<name>/<n>` or a path; `<name>` alone is its best finished iteration."""
    p = Path(ref)
    if (p / 'meta.json').exists():
        return store.Iteration(p.resolve())
    if '/' not in ref:
        it = best_iteration(ref)
        if it:
            return it
    return store.open_iteration(ref)


def series_parts(story_id):
    """[(episode id, title)] of stories/<id>/series.json, or None when `story_id` is not a series."""
    f = ROOT / 'stories' / story_id / 'series.json'
    if not f.exists():
        return None
    data = json.loads(f.read_text())
    return [(e['id'], e.get('title') or e['id']) for e in sorted(data.get('episodes', []), key=lambda e: e.get('n', 0))]


def story_title(name):
    """The `# Title` of stories/<name>/premise.md, else the name in words."""
    f = ROOT / 'stories' / name / 'premise.md'
    if f.exists():
        for line in f.read_text().splitlines():
            if line.startswith('# '):
                return line[2:].strip()
    return name.replace('-', ' ').replace('_', ' ').strip().title()


def _git_commit():
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def new_iteration(name, kind, extra=None):
    """runs/<name>/<NNNN>/ for something that is not a take (an assembly): meta.json with `kind`, the latest link."""
    project = RUNS / name
    project.mkdir(parents=True, exist_ok=True)
    numbers = [int(p.name) for p in project.iterdir() if p.is_dir() and p.name.isdigit()]
    it = store.Iteration(project / f'{max(numbers, default=0) + 1:04d}')
    it.path.mkdir(parents=True)
    it.cut.mkdir()
    meta = {'iteration': it.name, 'kind': kind, 'parent': None, 'created': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
            'videocraft': _git_commit(), **(extra or {})}
    (it.path / 'meta.json').write_text(json.dumps(meta, indent=2) + '\n')
    latest = project / 'latest'
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        os.symlink(it.name, latest)
    except OSError:
        pass
    return it


def window_for(width, height):
    """Window points for a framebuffer (a Mac is assumed 2x, as game.default_window does; the mod resizes if wrong)."""
    if sys.platform == 'darwin':
        return f'{width // 2}x{height // 2}'
    return f'{width}x{height}'


def take(script_path, say=print, timeout=900, slot_wait=1800, cut=True):
    """Takes a script through the same path as `videocraft run` (lint, take, cut, measure). Returns (iteration, code)."""
    from videocraft import cli, script
    plan, _ = script.compile_script(script.load(script_path), str(script_path))
    out = plan['output']
    window = window_for(out['width'], out['height'])
    return cli.run_take(Path(script_path), timeout=timeout, window=window, slot_wait=slot_wait, no_cut=not cut)


def reuse(project, script_text):
    """An iteration of runs/<project>/ whose script is byte-identical to `script_text` and passed (a cache hit)."""
    import hashlib
    sha = hashlib.sha256(script_text.encode()).hexdigest()[:16]
    for it in reversed(store.iterations(project)):
        try:
            meta = it.meta()
        except (OSError, ValueError):
            continue
        if meta.get('scriptSha') == sha and (it.result() or {}).get('verdict') == 'PASS':
            return it
    return None
