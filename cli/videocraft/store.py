"""The run store: every stage of every iteration on disk, so agents can compare iterations and hill-climb.

    runs/<script name>/
      index.json                  one line per iteration: verdict, scores, parent and chain, best (rewritten after each stage)
      climb.json, proposals/      the hill-climb's log and the scripts it proposed
      latest -> 0007              symlink to the newest iteration
      0007/
        meta.json                 iteration, parent, created, script and plan hashes, videocraft git commit
        script.toml               the script as authored (copy)
        plan.json                 what the mod played (compiled)
        edit.json                 the cut as compiled (order, trims, music, exports)
        take/                     written by the mod: result.json, game.log, shots/<name>/{video.mp4,frames.csv,marks.json}
        cut/                      written by the edit: <export>.mp4, graph.txt, poster.png
        measure/metrics.json      written by measure (stable keys; measure/__init__.py lists them)
        measure/report.md         the same for reading; measure/signals.csv the per-frame picture signals
        lint.json                 written by lint before the take
        review/packet/            strips, contact sheets, cut pairs, captions, prompts, packet.json (docs/REVIEW.md)
        review/<reviewer>.json    one per reviewer agent: scores per criterion, gates, notes, three fixes
        compare/<name>-<n>/       compare against another iteration: compare.md, compare.json, shots/*.png
        score.json                the aggregate the hill-climb compares
        notes.md                  what the agent changed from the parent and why

Owned by workstream (d). Paths here are a contract with every stage: add, never rename.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from videocraft.paths import ROOT, RUNS


class Iteration:
    def __init__(self, path: Path):
        self.path = path
        self.take = path / 'take'
        self.cut = path / 'cut'
        self.measure = path / 'measure'
        self.review = path / 'review'

    @property
    def name(self):
        return self.path.name

    def meta(self):
        return json.loads((self.path / 'meta.json').read_text())

    def result(self):
        f = self.take / 'result.json'
        return json.loads(f.read_text()) if f.exists() else None

    def edit(self):
        return json.loads((self.path / 'edit.json').read_text())

    def plan(self):
        return json.loads((self.path / 'plan.json').read_text())


def _sha(data: bytes):
    return hashlib.sha256(data).hexdigest()[:16]


def _git_commit():
    try:
        return subprocess.run(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def new_iteration(script_path: Path, plan: dict, edit: dict, parent: str | None = None) -> Iteration:
    project = RUNS / plan['name']
    project.mkdir(parents=True, exist_ok=True)
    numbers = [int(p.name) for p in project.iterdir() if p.is_dir() and p.name.isdigit()]
    n = max(numbers, default=0) + 1
    it = Iteration(project / f'{n:04d}')
    it.take.mkdir(parents=True)
    source = Path(script_path).read_bytes()
    shutil.copyfile(script_path, it.path / ('script' + Path(script_path).suffix))
    plan_text = json.dumps(plan, indent=2) + '\n'
    (it.path / 'plan.json').write_text(plan_text)
    (it.take / 'plan.json').write_text(plan_text)
    (it.path / 'edit.json').write_text(json.dumps(edit, indent=2) + '\n')
    meta = {'iteration': it.name, 'parent': parent, 'created': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
            'script': str(Path(script_path).resolve()), 'scriptSha': _sha(source), 'planSha': _sha(plan_text.encode()), 'videocraft': _git_commit()}
    (it.path / 'meta.json').write_text(json.dumps(meta, indent=2) + '\n')
    latest = project / 'latest'
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        os.symlink(it.name, latest)
    except OSError:
        pass
    update_index(project)
    return it


def open_iteration(ref: str) -> Iteration:
    """A path to an iteration, `<name>` (its latest) or `<name>/<number>`."""
    p = Path(ref)
    if (p / 'meta.json').exists():
        return Iteration(p.resolve())
    project, _, number = ref.partition('/')
    base = RUNS / project
    target = base / (f'{int(number):04d}' if number.isdigit() else number or 'latest')
    if not (target / 'meta.json').exists():
        raise SystemExit(f'No iteration {ref} (looked in {target})')
    return Iteration(target.resolve())


def iterations(project: str):
    base = RUNS / project
    return sorted((Iteration(p) for p in base.iterdir() if p.is_dir() and p.name.isdigit()), key=lambda i: i.name) if base.exists() else []


def _read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def summary(it):
    """One iteration's line in index.json: verdict, score, parent and the chain back to the first iteration."""
    meta = _read(it.path / 'meta.json') or {}
    result = it.result() or {}
    score = _read(it.path / 'score.json') or {}
    metrics = _read(it.measure / 'metrics.json') or {}
    shots = (metrics.get('picture') or {}).get('shot_stats') or {}
    return {'iteration': it.name, 'parent': meta.get('parent'), 'created': meta.get('created'), 'scriptSha': meta.get('scriptSha'),
            'verdict': result.get('verdict'), 'reason': result.get('reason'),
            'score': score.get('average'), 'minimum': score.get('minimum'), 'pass': score.get('pass'), 'rubric': score.get('rubric'),
            'criteria': score.get('criteria'), 'shots': shots.get('count'), 'medianShot': shots.get('median'),
            'seconds': (metrics.get('master') or {}).get('seconds'), 'notes': (it.path / 'notes.md').exists()}


def _parent_name(ref):
    """`0003`, `3`, `hello/3` or a path → the iteration folder name, or None."""
    if not ref:
        return None
    tail = str(ref).rstrip('/').split('/')[-1]
    return f'{int(tail):04d}' if tail.isdigit() else tail


def update_index(project: Path):
    """Rewrites runs/<name>/index.json from what is on disk (every stage calls it; it is cheap and idempotent)."""
    its = sorted((Iteration(p) for p in project.iterdir() if p.is_dir() and p.name.isdigit()), key=lambda i: i.name)
    rows = {i.name: summary(i) for i in its}
    for row in rows.values():
        chain, seen, cur = [], set(), _parent_name(row['parent'])
        while cur and cur in rows and cur not in seen:
            chain.append(cur)
            seen.add(cur)
            cur = _parent_name(rows[cur]['parent'])
        row['chain'] = chain
    scored = [r for r in rows.values() if r['score'] is not None and r['verdict'] == 'PASS']
    best = max(scored, key=lambda r: (r['score'], r['iteration']))['iteration'] if scored else None
    index = {'name': project.name, 'best': best, 'iterations': list(rows.values())}
    (project / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    return index
