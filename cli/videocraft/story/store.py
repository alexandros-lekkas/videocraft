"""The story store: every revision of every stage on disk, and the chosen ("locked") ones committed in stories/.

    runs/story/<story-id>/                 every draft, never committed (runs/ is git-ignored)
      index.json                           per stage: revisions (rev, file, parent, note, source, created, sha,
                                           inputs = the upstream stages' shas it was drafted from) and `locked`
      premise/0001.md  bible/0001.toml  outline/0003.md  script/0002.md  shots/0004.toml (+ 0004.plan.json)
    stories/<story-id>/                    the human-readable source of truth, committed
      story.json                           id, format, vertical, series links, the locked rev and sha of each stage
      premise.md  bible.toml  outline.md  script.md  shots.toml

A fresh clone has stories/ but no runs/: the store imports each locked file as revision 1, so drafting continues.
An episode of a series has no bible of its own: story.json `bible_from` names the series story whose bible it reads.
Paths are a contract (docs/STORY.md): add, never rename.
"""
import datetime
import hashlib
import json
import os
import re
from pathlib import Path

from videocraft.paths import ROOT, RUNS

STAGES = ('premise', 'bible', 'outline', 'script', 'shots')
EXT = {'premise': 'md', 'bible': 'toml', 'outline': 'md', 'script': 'md', 'shots': 'toml'}
FILES = {stage: f'{stage}.{ext}' for stage, ext in EXT.items()}
FORMATS = {'short': (30, 90), 'episode': (180, 480), 'long': (600, 1200)}
STORY_ID = re.compile(r'^[a-z0-9][a-z0-9-]{0,47}$')


class StoryError(ValueError):
    """A problem an agent can act on: what is wrong and the command that fixes it."""


def slug(text, limit=40):
    words = re.findall(r'[a-z0-9]+', text.lower())
    out = ''
    for w in words:
        if len(out) + len(w) + 1 > limit:
            break
        out = f'{out}-{w}' if out else w
    return out or 'story'


def sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


class Store:
    def __init__(self, runs=None, stories=None):
        self.runs = Path(runs) if runs else Path(os.environ.get('VIDEOCRAFT_STORY_RUNS') or RUNS / 'story')
        self.stories = Path(stories) if stories else Path(os.environ.get('VIDEOCRAFT_STORIES') or ROOT / 'stories')

    # Stories ----------------------------------------------------------------------------------------------------

    def story_dir(self, sid):
        return self.stories / sid

    def run_dir(self, sid):
        return self.runs / sid

    def exists(self, sid):
        return (self.story_dir(sid) / 'story.json').exists()

    def ids(self):
        return sorted(p.parent.name for p in self.stories.glob('*/story.json')) if self.stories.exists() else []

    def create(self, sid, fmt='short', vertical=False, **extra):
        if not STORY_ID.match(sid):
            raise StoryError(f'story id "{sid}": lowercase letters, digits and dashes, up to 48 characters')
        if fmt not in FORMATS:
            raise StoryError(f'format "{fmt}": one of {", ".join(FORMATS)}')
        if self.exists(sid):
            raise StoryError(f'story "{sid}" exists (stories/{sid}/); use `story draft` or `story revise`, or pick --id')
        meta = {'id': sid, 'format': fmt, 'vertical': bool(vertical), 'created': _now(), 'series': None,
                'episode': None, 'bible_from': None, 'stages': {}}
        meta.update({k: v for k, v in extra.items() if v is not None})
        self.save_meta(sid, meta)
        self.index(sid)
        return meta

    def meta(self, sid):
        f = self.story_dir(sid) / 'story.json'
        if not f.exists():
            known = ', '.join(self.ids()) or 'none yet'
            raise StoryError(f'no story "{sid}" (looked for {f}); stories: {known}. Start one with `story new "<premise>"`')
        return json.loads(f.read_text(encoding='utf-8'))

    def save_meta(self, sid, meta):
        _write_json(self.story_dir(sid) / 'story.json', meta)

    # Revisions --------------------------------------------------------------------------------------------------

    def index(self, sid):
        f = self.run_dir(sid) / 'index.json'
        if f.exists():
            return json.loads(f.read_text(encoding='utf-8'))
        meta = self.meta(sid)
        index = {'id': sid, 'stages': {stage: {'locked': None, 'revisions': []} for stage in STAGES}}
        # A fresh clone: the committed (locked) files become revision 1 so the history continues from them.
        for stage in STAGES:
            locked = self.story_dir(sid) / FILES[stage]
            if locked.exists():
                text = locked.read_text(encoding='utf-8')
                rel = f'{stage}/0001.{EXT[stage]}'
                (self.run_dir(sid) / stage).mkdir(parents=True, exist_ok=True)
                (self.run_dir(sid) / rel).write_text(text, encoding='utf-8')
                info = meta['stages'].get(stage, {})
                index['stages'][stage] = {'locked': 1, 'revisions': [{
                    'rev': 1, 'file': rel, 'parent': None, 'note': 'imported from stories/', 'source': 'locked',
                    'created': _now(), 'sha': sha(text), 'inputs': info.get('inputs', {})}]}
        self._save_index(sid, index)
        return index

    def _save_index(self, sid, index):
        _write_json(self.run_dir(sid) / 'index.json', index)

    def revisions(self, sid, stage):
        return self.index(sid)['stages'][stage]['revisions']

    def revision(self, sid, stage, rev):
        for r in self.revisions(sid, stage):
            if r['rev'] == rev:
                return r
        have = ', '.join(str(r['rev']) for r in self.revisions(sid, stage)) or 'none'
        raise StoryError(f'{sid} {stage}: no revision {rev} (revisions: {have})')

    def revision_path(self, sid, stage, rev):
        return self.run_dir(sid) / self.revision(sid, stage, rev)['file']

    def add(self, sid, stage, text, parent=None, note=None, source='model', inputs=None):
        """Stores a new revision (never overwrites one) and returns its number."""
        if stage not in STAGES:
            raise StoryError(f'stage "{stage}": one of {", ".join(STAGES)}')
        index = self.index(sid)
        entry = index['stages'][stage]
        rev = max((r['rev'] for r in entry['revisions']), default=0) + 1
        rel = f'{stage}/{rev:04d}.{EXT[stage]}'
        path = self.run_dir(sid) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        text = text if text.endswith('\n') else text + '\n'
        path.write_text(text, encoding='utf-8')
        entry['revisions'].append({'rev': rev, 'file': rel, 'parent': parent, 'note': note, 'source': source,
                                   'created': _now(), 'sha': sha(text), 'inputs': inputs or {}})
        self._save_index(sid, index)
        return rev

    def lock(self, sid, stage, rev):
        """Makes a revision the chosen one: copied to stories/<id>/, recorded in story.json and index.json."""
        r = self.revision(sid, stage, rev)
        text = (self.run_dir(sid) / r['file']).read_text(encoding='utf-8')
        (self.story_dir(sid) / FILES[stage]).write_text(text, encoding='utf-8')
        meta = self.meta(sid)
        meta['stages'][stage] = {'rev': rev, 'sha': r['sha'], 'inputs': r['inputs']}
        self.save_meta(sid, meta)
        index = self.index(sid)
        index['stages'][stage]['locked'] = rev
        self._save_index(sid, index)

    def locked(self, sid, stage):
        return self.index(sid)['stages'][stage]['locked']

    def current(self, sid, stage):
        """The revision number the next stage reads: the locked one, else the newest."""
        entry = self.index(sid)['stages'][stage]
        if entry['locked'] is not None:
            return entry['locked']
        return entry['revisions'][-1]['rev'] if entry['revisions'] else None

    def source_of(self, sid, stage):
        """(story id, stage) that holds this stage's text: an episode's bible lives in its series story."""
        if stage == 'bible':
            owner = self.meta(sid).get('bible_from')
            if owner and owner != sid:
                return owner, stage
        return sid, stage

    def text(self, sid, stage, rev=None):
        """The text of a stage: a given revision, else the locked file, else the newest revision; None if absent."""
        owner, stage = self.source_of(sid, stage)
        if rev is not None:
            return self.revision_path(owner, stage, rev).read_text(encoding='utf-8')
        locked = self.story_dir(owner) / FILES[stage]
        if locked.exists():
            return locked.read_text(encoding='utf-8')
        cur = self.current(owner, stage)
        return None if cur is None else self.revision_path(owner, stage, cur).read_text(encoding='utf-8')

    def path(self, sid, stage):
        """The file a person (or `videocraft run`) opens for this stage."""
        owner, stage = self.source_of(sid, stage)
        return self.story_dir(owner) / FILES[stage]

    def shas(self, sid, stages):
        """{stage: sha} of this story's current stages; a key `<story>:<stage>` names another story's stage."""
        out = {}
        for key in stages:
            owner, _, stage = key.rpartition(':')
            t = self.text(owner or sid, stage)
            if t is not None:
                out[key] = sha(t)
        return out

    def stale(self, sid, stage):
        """Upstream stages that changed since this stage's current revision was drafted from them."""
        cur = self.current(*self.source_of(sid, stage))
        if cur is None:
            return []
        owner, _ = self.source_of(sid, stage)
        inputs = self.revision(owner, stage, cur)['inputs']
        now = self.shas(sid, list(inputs))
        return [s for s, h in inputs.items() if now.get(s) != h]
