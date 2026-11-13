"""measure/report.md: metrics.json for a person or a reviewer agent to read in one pass."""
from pathlib import Path


def _tc(seconds):
    m, s = divmod(max(0.0, seconds), 60)
    return f'{int(m)}:{s:05.2f}'


def _fmt(v, unit=''):
    return '-' if v is None else f'{v:g}{unit}' if isinstance(v, (int, float)) else str(v)


def write_report(m, path, title='', plan=None):
    L = [f'# Measure: {title}', '']
    v = m['master']
    L.append(f'{v["width"]}x{v["height"]} at {v["fps"]:.3f} fps, {v["frames"]} frames, {v["seconds"]:.2f} s, '
             f'{v["bytes"] / 1e6:.1f} MB, {"with" if v.get("audio") else "no"} audio.')
    if 'checks' in m:
        bad = [k for k, ok in m['checks'].items() if not ok]
        L.append(f'Format checks: {"all pass" if not bad else "FAIL " + ", ".join(bad)} (expected {m["expectedFrames"]} frames).')
    src = m.get('source', {})
    if src.get('kind') == 'video' and (src.get('from') or src.get('to')):
        L.append(f'Measured stretch: {_fmt(src.get("from") or 0)} to {_fmt(src.get("to"))} s; times below are from its start.')
    L.append('')

    pic = m.get('picture')
    if pic:
        st = pic['shot_stats']
        L += ['## Shots', '']
        if st.get('count'):
            hist = ' · '.join(f'{k} s: {n}' for k, n in st['histogram'].items())
            L.append(f'**{st["count"]} shots** in {pic["seconds"]:.1f} s ({st["per_minute"]:g} a minute); median **{st["median"]:.2f} s**, '
                     f'mean {st["mean"]:.2f} s, longest {st["longest"]:.2f} s, shortest {st["shortest"]:.2f} s; over 7.5 s: {st["over_7_5s"]}.')
            L.append(f'Lengths: {hist}.')
            for r in st['short_runs']:
                L.append(f'A run of {r["shots"]} shots under 0.6 s from shot {r["first"] + 1}.')
        L.append(f'Black: {len(pic["black"])} stretch(es), {pic["black_seconds"]:.2f} s in all'
                 + (': ' + ', '.join(f'{_tc(b["start"])}-{_tc(b["end"])}' for b in pic['black']) if pic['black'] else '') + '.')
        if pic['frozen']:
            L.append(f'Frozen (identical frames, 3 or more): {len(pic["frozen"])} run(s); longest '
                     f'{max(f["end"] - f["start"] for f in pic["frozen"]):.2f} s.')
        if pic['duplicate_at_cuts']:
            L.append('Repeated frame at a cut: ' + ', '.join(_tc(d['t']) for d in pic['duplicate_at_cuts']) + '.')
        L += ['', '| # | Start | Length (s) | Frames |', '|--:|--:|--:|:--|']
        for s in pic['shots']:
            L.append(f'| {s["index"] + 1} | {_tc(s["start"])} | {s["seconds"]:.2f} | {s["frames"][0]}-{s["frames"][1] - 1} |')
        L.append('')
    cc = m.get('cut_check')
    if cc:
        L.append(f'Cuts in the edit: {len(cc["expected"])} hard ({cc["matched"]} seen in the picture), {len(cc["soft"])} soft (fades, black).'
                 + (f' Not seen: frames {cc["missed"]}.' if cc['missed'] else '')
                 + (f' Jumps inside clips: frames {cc["extra"]}.' if cc['extra'] else ''))
        L.append('')

    ld = m.get('loudness')
    L += ['## Sound', '']
    if ld:
        L.append(f'Integrated **{_fmt(ld["integrated"], " LUFS")}**, true peak {_fmt(ld["true_peak"], " dBFS")}, range {_fmt(ld["lra"], " LU")}.')
        if ld['silences']:
            L.append('Silence (under -50 LUFS momentary): ' + ', '.join(f'{_tc(s["start"])}-{_tc(s["end"])}' for s in ld['silences']) + '.')
        L.append('Momentary loudness per second: ' + ' '.join(_fmt(x) for x in ld['momentary_per_second']))
    else:
        L.append('No audio stream.')
    L.append('')

    L += balance_lines(m.get('balance'))

    dl = m.get('dialogue')
    if dl:
        L += ['## Dialogue pace', '']
        L.append(f'**{len(dl["lines"])} voiced line(s)**; a voice for **{dl["voice_seconds"]:.2f} s** of {dl["runtime"]:.2f} s '
                 f'(**{dl["voice_share"]:.0%}** of the runtime); median **{_fmt(dl["median_wps"] and round(dl["median_wps"], 2))} words a second** '
                 f'(lines of 3 words or more; slow under 2.6, the default pace 3.2); first word at {_tc(dl["lead_in"])}.')
        dead = dl.get('dead_air') or []
        L.append(f'Dead air (over 0.8 s without a voice inside dialogue): '
                 + (', '.join(f'{_tc(g["start"])}-{_tc(g["end"])} ({g["seconds"]:.2f} s)' for g in dead) if dead else 'none') + '.')
        if dl.get('longest_silences'):
            L.append('Longest silences between lines: ' + ', '.join(
                f'{g["seconds"]:.2f} s at {_tc(g["start"])} ({g["after"]} to {g["before"]}{", " + g["excused"] if g["excused"] else ""})'
                for g in dl['longest_silences']) + '.')
        L += ['', '| Line | Character | Shot | Start | Words | Words/s |', '|:--|:--|:--|--:|--:|--:|']
        for l in dl['lines']:
            L.append(f'| {l["id"]} | {l["character"]} | {l["shot"]} | {_tc(l["start"])} | {l["words"]} | {"-" if l["wps"] is None else format(l["wps"], ".2f")}'
                     + (' (beat)' if l.get('beat') else '') + (f' ({l["style"]})' if l.get('style') else '') + ' |')
        L.append('')
    if m.get('camera'):
        L += ['## Camera and framing', '', '| Shot | Rig | Speed med/max (b/s) | Vertical jerk p95 (b/s³) | Turn p95 (°/s) | Subject x med (min-max) | Height med | Size change | Flags |',
              '|:--|:--|--:|--:|--:|:--|--:|--:|:--|']
        for name, c in m['camera'].items():
            f = (m.get('framing') or {}).get(name, {})
            sp, vj, tn = c.get('speed') or {}, c.get('vertical_jerk') or {}, c.get('turn') or {}
            fx = f.get('x')
            L.append(f'| {name} | {c.get("rig")} | {_fmt(sp.get("median"))}/{_fmt(sp.get("max"))} | {_fmt(vj.get("p95"))} | {_fmt(tn.get("p95"))} | '
                     + (f'{fx["median"]:.2f} ({fx["min"]:.2f}-{fx["max"]:.2f})' if fx else '-') + ' | '
                     + (f'{f["height"]["median"]:.2f}' if f.get('height') else '-') + ' | '
                     + (f'{f["size_change"]:.0%}' if 'size_change' in f else '-') + ' | ' + ('; '.join(f.get('flags', [])) or '-') + ' |')
        L.append('')
    tx = m.get('text')
    if tx is not None and 'items' in tx:
        L += ['## Text', '']
        if not tx['items']:
            L.append('No text.json in any shot (no text on screen, or the text layer did not log it).')
        else:
            L += ['| Shot | Frames | Text | Words | On (s) | Complete (s) | Needs (s) | Words/s | Cap px |', '|:--|:--|:--|--:|--:|--:|--:|--:|--:|']
            for t in tx['items']:
                L.append(f'| {t["shot"]} | {t["start"]}-{t["end"]} | {t["text"][:40]} | {t["words"]} | {t["seconds"]:.2f} | {t["complete_seconds"]:.2f} | '
                         f'{t["reading_seconds"]:.2f} | {t["words_per_second"]:.2f} | {_fmt(t["cap_height"])} |')
            L.append('')
            L.append('Rule problems: ' + (', '.join(f'{k} {n}' for k, n in tx['counts'].items()) or 'none') + '.')
        L.append('')
    if m.get('warnings'):
        L += ['## Look at', ''] + [f'- {w}' for w in m['warnings']] + ['']
    Path(path).write_text('\n'.join(L))


def balance_lines(b):
    """The "Mix balance" section (cut/audio.json `balance`, also in the review's sound sheet): what sits over what."""
    if not b:
        return []
    v, mu, sx, r = b.get('voice') or {}, b.get('music') or {}, b.get('sfx') or {}, b.get('ratio') or {}
    L = ['## Mix balance', '',
         'Measured on the mix\'s own buses at the master\'s gain (the master alone cannot tell voice from music); '
         'LUFS from 400 ms momentary readings, a line\'s value the power mean of the readings inside it.', '',
         f'- Voice: short-term median **{_fmt(v.get("short_term_median"), " LUFS")}** (max {_fmt(v.get("short_term_max"))}), '
         f'integrated {_fmt(v.get("integrated"))}.',
         f'- Music: **{_fmt(mu.get("under_voice"), " LUFS")} under lines**, **{_fmt(mu.get("between_lines"), " LUFS")} between lines** '
         f'(95th percentile {_fmt(mu.get("between_lines_p95"))}).',
         f'- Voice over music: median **{_fmt(r.get("median"), " LU")}**, least **{_fmt(r.get("min"), " LU")}**; '
         + (f'**{len(r["close"])} line(s) under {r.get("warn_under"):g} LU**: {", ".join(map(str, r["close"]))}.' if r.get('close')
            else f'no line under {_fmt(r.get("warn_under"))} LU.'),
         f'- Effects: loudest momentary {_fmt(sx.get("momentary_max"), " LUFS")}, integrated {_fmt(sx.get("integrated"))}'
         + (f'; held under the voice in {sx["limited"]["stretches"]} reading(s), at most {sx["limited"]["deepest_db"]} dB' if sx.get('limited') else '') + '.']
    t = b.get('targets')
    if t:
        L.append(f'- Targets: voice {t.get("voice_level")} LUFS before the master, music {t.get("music_level")} LUFS between lines, '
                 f'{t.get("music_under_voice")} LU under the voice, the duck at least {t.get("least")} dB'
                 + (f', game track trim {t.get("game_trim")} dB' if t.get('game_trim') else '') + '.')
    if b.get('lines'):
        L += ['', '| Line | Character | Start | Voice | Music | Effects | Voice over music |', '|:--|:--|--:|--:|--:|--:|--:|']
        for l in b['lines']:
            L.append(f'| {l["id"]} | {l.get("character") or "-"} | {_tc(l["start"])} | {_fmt(l["voice"])} | {_fmt(l["music"])} | '
                     f'{_fmt(l.get("sfx"))} | {_fmt(l.get("ratio"))}' + (' **close**' if l.get('id') in (r.get('close') or []) else '') + ' |')
    L.append('')
    return L
