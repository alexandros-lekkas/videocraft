"""One place that asks a model something: `ask(prompt, images=(), schema=None, model=None) -> str`.

Backends, chosen per call (VIDEOCRAFT_AGENT=claude|api forces one):
  claude  the local Claude Code CLI on PATH (`claude -p`): images are files it reads with its Read tool; no key
          needed. Detected, never required.
  api     the Anthropic Messages API when ANTHROPIC_API_KEY is set: images are sent inline (JPEG, at most 1568 px on
          the long side, made with ffmpeg). Uses the `anthropic` package when it happens to be installed, else plain
          urllib (the CLI stays standard library only).
The default model is claude-opus-5-5 (VIDEOCRAFT_MODEL overrides). `schema` is a JSON Schema the answer must meet:
the CLI gets it as --json-schema, the API as a structured-output format; either way the text returned is the answer
(parse it with review.reviews.extract_json). Shared by review, climb and other command groups. Owned by (d).
"""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from videocraft import tools

DEFAULT_MODEL = 'claude-opus-5-5'
API_URL = 'https://api.anthropic.com/v1/messages'
MAX_IMAGES = 60
LONG_EDGE = 1568


class AgentError(RuntimeError):
    pass


def model_name(model=None):
    return model or os.environ.get('VIDEOCRAFT_MODEL') or DEFAULT_MODEL


def backend():
    """'claude', 'api' or None: what ask() would use now."""
    forced = os.environ.get('VIDEOCRAFT_AGENT')
    if forced in ('claude', 'api'):
        return forced
    if shutil.which('claude'):
        return 'claude'
    if os.environ.get('ANTHROPIC_API_KEY'):
        return 'api'
    return None


def ask(prompt, images=(), schema=None, model=None, timeout=1800, effort='high'):
    images = [Path(p) for p in images][:MAX_IMAGES]
    which = backend()
    if which == 'claude':
        return _ask_cli(prompt, images, schema, model_name(model), timeout, effort)
    if which == 'api':
        return _ask_api(prompt, images, schema, model_name(model), timeout, effort)
    raise AgentError('No model to ask: put the `claude` CLI on PATH or set ANTHROPIC_API_KEY')


def _ask_cli(prompt, images, schema, model, timeout, effort):
    dirs = sorted({str(p.resolve().parent) for p in images})
    if images:
        prompt += '\n\n## Image files to read\n\nRead every one of these image files with the Read tool before you answer:\n' + \
                  '\n'.join(f'- {p.resolve()}' for p in images) + '\n'
    cmd = ['claude', '-p', '--model', model, '--output-format', 'json', '--no-session-persistence', '--allowedTools', 'Read']
    if effort:
        cmd += ['--effort', effort]
    for d in dirs:
        cmd += ['--add-dir', d]
    if schema:
        cmd += ['--json-schema', json.dumps(schema)]
    workdir = dirs[0] if dirs else tempfile.gettempdir()
    try:
        done = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=workdir)
    except subprocess.TimeoutExpired as e:
        raise AgentError(f'claude -p took longer than {timeout} s') from e
    if done.returncode != 0:
        raise AgentError(f'claude -p failed ({done.returncode}): {(done.stderr or done.stdout)[-800:]}')
    try:
        envelope = json.loads(done.stdout)
    except json.JSONDecodeError:
        return done.stdout
    if envelope.get('is_error'):
        raise AgentError(f'claude -p: {envelope.get("result") or envelope}')
    structured = envelope.get('structured_output')
    if structured is not None:
        return '```json\n' + json.dumps(structured, indent=2) + '\n```'
    return envelope.get('result', '')


def _jpeg(path, out_dir):
    target = Path(out_dir) / (path.stem + '.jpg')
    subprocess.run([tools.ffmpeg(), '-v', 'error', '-y', '-i', str(path), '-vf',
                    f"scale='min({LONG_EDGE},iw)':'min({LONG_EDGE},ih)':force_original_aspect_ratio=decrease", '-q:v', '3', str(target)], check=True)
    return target


def _ask_api(prompt, images, schema, model, timeout, effort):
    key = os.environ.get('ANTHROPIC_API_KEY')
    if not key:
        raise AgentError('ANTHROPIC_API_KEY is not set')
    content = []
    with tempfile.TemporaryDirectory(prefix='videocraft-agent-') as tmp:
        for p in images:
            data = base64.standard_b64encode(_jpeg(p, tmp).read_bytes()).decode('ascii')
            content.append({'type': 'text', 'text': f'Image: {p.name}'})
            content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': 'image/jpeg', 'data': data}})
    content.append({'type': 'text', 'text': prompt})
    body = {'model': model, 'max_tokens': 16000, 'messages': [{'role': 'user', 'content': content}],
            'fallbacks': 'default'}   # server-side refusal fallback (beta header below)
    output_config = {}
    if effort:
        output_config['effort'] = effort
    if schema:
        output_config['format'] = {'type': 'json_schema', 'schema': schema}
    if output_config:
        body['output_config'] = output_config
    try:
        import anthropic  # optional; the CLI never requires it
        client = anthropic.Anthropic(api_key=key, timeout=timeout)
        reply = client.beta.messages.create(betas=['server-side-fallback-2026-07-01'], **body).to_dict()
    except ImportError:
        request = urllib.request.Request(API_URL, data=json.dumps(body).encode(), method='POST', headers={
            'x-api-key': key, 'anthropic-version': '2023-06-01', 'anthropic-beta': 'server-side-fallback-2026-07-01',
            'content-type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                reply = json.loads(response.read())
        except urllib.error.HTTPError as e:
            raise AgentError(f'Anthropic API {e.code}: {e.read().decode(errors="replace")[:800]}') from e
        except urllib.error.URLError as e:
            raise AgentError(f'Anthropic API unreachable: {e.reason}') from e
    if reply.get('stop_reason') == 'refusal':
        raise AgentError(f'the model declined: {reply.get("stop_details")}')
    text = ''.join(b.get('text', '') for b in reply.get('content', []) if b.get('type') == 'text')
    if schema and text.strip().startswith('{'):
        text = '```json\n' + text + '\n```'
    return text
