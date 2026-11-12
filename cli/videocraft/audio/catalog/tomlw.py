"""Just enough of a TOML writer for the generated catalogs (tomllib reads; the standard library has no writer):
strings, numbers, booleans, lists of those, inline tables, and [section] / [section."key"] tables."""
import math
import re

BARE = re.compile(r'^[A-Za-z0-9_-]+$')


def key(k):
    return k if BARE.match(k) else string(k)


def string(s):
    s = str(s).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    return f'"{s}"'


def value(v):
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            raise ValueError('no NaN or inf in the catalog')
        text = f'{v:.4f}'.rstrip('0')
        return text + '0' if text.endswith('.') else text
    if isinstance(v, str):
        return string(v)
    if isinstance(v, (list, tuple)):
        return '[' + ', '.join(value(x) for x in v) + ']'
    if isinstance(v, dict):
        return '{ ' + ', '.join(f'{key(k)} = {value(x)}' for k, x in v.items() if x is not None) + ' }' if v else '{}'
    raise TypeError(f'cannot write {type(v).__name__} to TOML')


def table(name, fields):
    """`[name]` then `k = v` per field (None skipped)."""
    lines = [f'[{name}]']
    lines += [f'{key(k)} = {value(v)}' for k, v in fields.items() if v is not None]
    return '\n'.join(lines) + '\n'


def inline_rows(name, rows):
    """`[name]` then one `"id" = { … }` line per row: one greppable line per sound."""
    lines = [f'[{name}]']
    lines += [f'{key(k)} = {value(v)}' for k, v in rows.items()]
    return '\n'.join(lines) + '\n'
