"""measure/report.md: metrics.json for a person or a reviewer agent to read in one pass."""


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
    open(path, 'w').write('\n'.join(L))
