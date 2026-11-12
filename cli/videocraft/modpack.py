"""`videocraft modpack`: modpack/pack.toml → build/modpack/<name>-<version>.mrpack (Modrinth's pack format).

An .mrpack is a zip with modrinth.index.json (format 1): every mod as a download from Modrinth's CDN with its sha1,
sha512 and size, resolved here through Modrinth's public API (api.modrinth.com/v2, no key), and only videocraft's
own jar under overrides/mods/. Nothing third-party is redistributed. Owned by workstream (d).
"""
import json
import tomllib
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from videocraft import __version__
from videocraft.paths import ROOT

API = 'https://api.modrinth.com/v2'
AGENT = f'videocraft-modpack/{__version__}'


class PackError(RuntimeError):
    pass


def _get(url, timeout=30):
    request = urllib.request.Request(url, headers={'User-Agent': AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def resolve(slug, version, minecraft, fetch=_get):
    """The file entry of one mod version for modrinth.index.json."""
    query = urllib.parse.urlencode({'loaders': json.dumps(['fabric']), 'game_versions': json.dumps([minecraft])})
    versions = fetch(f'{API}/project/{urllib.parse.quote(slug)}/version?{query}')
    match = next((v for v in versions if v.get('version_number') == version), None)
    if not match:
        have = ', '.join(v.get('version_number', '?') for v in versions[:6])
        raise PackError(f'{slug} {version} is not on Modrinth for Fabric {minecraft} (have: {have or "none"})')
    f = next((f for f in match['files'] if f.get('primary')), match['files'][0])
    return {'path': f'mods/{f["filename"]}', 'hashes': {'sha1': f['hashes']['sha1'], 'sha512': f['hashes']['sha512']},
            'env': {'client': 'required', 'server': 'optional'}, 'downloads': [f['url']], 'fileSize': f['size']}


def index(pack, fetch=_get):
    p = pack['pack']
    files = [resolve(m['slug'], m['version'], p['minecraft'], fetch) for m in pack.get('mod', [])]
    return {'formatVersion': 1, 'game': 'minecraft', 'versionId': p.get('version', __version__), 'name': p['name'],
            'summary': p.get('summary', 'Agent-directed video for Minecraft Java'), 'files': files,
            'dependencies': {'minecraft': p['minecraft'], 'fabric-loader': p['fabric_loader']}}


def build(pack_file=None, jar=None, out_dir=None, fetch=_get):
    pack_file = Path(pack_file or ROOT / 'modpack/pack.toml')
    pack = tomllib.loads(pack_file.read_text())
    jars = sorted((ROOT / 'build/libs').glob('videocraft-*.jar'))
    jars = [j for j in jars if not j.name.endswith(('-sources.jar', '-dev.jar'))]
    jar = Path(jar) if jar else (jars[-1] if jars else None)
    if not jar or not jar.exists():
        raise PackError('No videocraft jar: ./gradlew build first (or --jar <file>)')
    data = index(pack, fetch)
    out_dir = Path(out_dir or ROOT / 'build/modpack')
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f'{pack["pack"]["name"]}-{data["versionId"]}.mrpack'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('modrinth.index.json', json.dumps(data, indent=2) + '\n')
        z.write(jar, f'overrides/mods/{jar.name}')
    return target, data
