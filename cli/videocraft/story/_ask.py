"""The model call for the story pipeline.

Uses `videocraft.agents.ask` (the CLI workstream's single model module) when it exists. Until then, a minimal
stand-in with the same signature: a local agent CLI (`claude -p`) when one is on PATH, else a clear error. Tests
replace `ask` here with a fake (story.stages takes an `ask` argument), so nothing in the test suite calls a model.
"""
import os
import shutil
import subprocess

DEFAULT_MODEL = os.environ.get('VIDEOCRAFT_STORY_MODEL') or 'claude-opus-5-5'


class AskError(RuntimeError):
    """No model is available, or the model call failed: what happened and how to proceed without one."""


def ask(prompt, images=(), schema=None, model=None):
    try:
        from videocraft import agents  # the CLI workstream's module, once it lands
    except ImportError:
        agents = None
    if agents is not None and callable(getattr(agents, 'ask', None)):
        return agents.ask(prompt, images=images, schema=schema, model=model or DEFAULT_MODEL)
    return _claude_cli(prompt, images, schema, model or DEFAULT_MODEL)


def _claude_cli(prompt, images, schema, model):
    exe = shutil.which('claude')
    if not exe:
        raise AskError('no model available: videocraft.agents is missing and no `claude` CLI is on PATH. '
                       'Write the stage by hand and pass it with --from-file (docs/STORY.md).')
    if images:
        prompt += '\n\nImages to look at (read them from disk):\n' + '\n'.join(str(i) for i in images)
    if schema is not None:
        import json
        prompt += '\n\nReply with JSON only, matching this JSON schema:\n' + json.dumps(schema, indent=2)
    timeout = float(os.environ.get('VIDEOCRAFT_ASK_TIMEOUT') or 1800)
    try:
        done = subprocess.run([exe, '-p', '--model', model, '--output-format', 'text'], input=prompt,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise AskError(f'the model call timed out after {timeout:.0f} s') from e
    if done.returncode != 0:
        raise AskError(f'`claude -p` exited {done.returncode}: {(done.stderr or done.stdout).strip()[:400]}')
    return done.stdout
