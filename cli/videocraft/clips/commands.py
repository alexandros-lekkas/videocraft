"""`videocraft assemble` and `videocraft clips find|cut|pack` (docs/CLIPS.md)."""
import json


def say(text=''):
    print(text, flush=True)


def _parts(refs, titles):
    from videocraft.clips import runs
    parts = []
    if len(refs) == 1 and runs.series_parts(refs[0]):
        for ep, title in runs.series_parts(refs[0]):
            it = runs.best_iteration(ep)
            if not it:
                raise SystemExit(f'episode {ep} of the series {refs[0]} has no finished run in runs/{ep}/ (videocraft run its shots.toml)')
            parts.append((it, title))
    else:
        for ref in [r for arg in refs for r in arg.split(',') if r]:
            it = runs.resolve(ref)
            parts.append((it, runs.story_title(it.path.parent.name)))
    for k, title in enumerate(titles or []):
        if k < len(parts):
            parts[k] = (parts[k][0], title)
    return parts


def cmd_assemble(args):
    from videocraft.clips import assemble
    parts = _parts(args.parts, args.title)
    out, record = assemble.assemble(parts, args.output, cards=args.cards, card_seconds=args.card_seconds, cold_open=args.cold_open,
                                    label=args.label, measure_it=not args.no_measure, say=say)
    lufs = record['loudness']['master']
    for p in record['loudness']['parts']:
        if p['kind'] == 'part':
            say(f'  part  {p["title"][:40]:40}  {p.get("before", "-")} LUFS -> {p.get("after", "-")} LUFS in the master')
    for problem in record['chapter_problems']:
        say(f'  chapters: {problem}')
    say(f'RESULT   PASS {record["width"]}x{record["height"]} {record["fps"]} fps {record["frames"]} frames {record["seconds"]:.2f} s; '
        f'{len(record["chapters"])} chapters; {lufs["integrated"]:.1f} LUFS, true peak {lufs["true_peak"]:.1f} dBTP')
    say(f'VIDEO    {out.cut / "master.mp4"}')
    say(f'CHAPTERS {out.cut / "chapters.txt"}')
    say(f'RUN      {out.path}')
    say(f'TIME     {record["seconds_taken"]:.0f} s')
    return 0


def cmd_find(args):
    from videocraft.clips import moments, runs
    it = runs.resolve(args.target)
    data = moments.find(it, shortest=args.min, longest=args.max, ask=args.ask, model=args.model, say=say)
    for m in data['moments'][:args.show]:
        say(f'  #{m["n"]:<2} {m["start"]:7.2f}-{m["end"]:7.2f} s ({m["seconds"]:5.2f} s)  score {m["score"]:5.2f}  {m["title"][:48]}')
        for r in m['reasons'][:4]:
            say(f'        {r}')
    say(f'MOMENTS  {len(data["moments"])} ranked; {it.path / "clips" / "moments.json"}')
    return 0 if data['moments'] else 1


def cmd_cut(args):
    from videocraft.clips import runs, shorts
    it = runs.resolve(args.target)
    record = shorts.cut(it, moment=args.moment, start=args.start, end=args.end, method=args.method, aspect=args.aspect,
                        subject=args.subject, hook=args.hook, pull=args.pull, say=say, timeout=args.timeout)
    say(f'RESULT   {"PASS" if record["pass"] else "FAIL"} {record["width"]}x{record["height"]} {record["seconds"]:.2f} s by {record["method"]}; '
        + '; '.join(record['checks_text']))
    say(f'VIDEO    {record["video"]}')
    say(f'CLIP     {record["folder"]}')
    return 0 if record['pass'] else 1


def cmd_pack(args):
    from videocraft.clips import pack, runs
    it = runs.resolve(args.target)
    packed = pack.pack(it, ask=args.ask, model=args.model, say=say)
    for meta in packed:
        say(f'  {meta["clip"]:4} {meta["title"][:60]}')
        say(f'       thumbnail {meta["thumbnail"]["file"]} (t {meta["thumbnail"]["t"]:.2f} s: {meta["thumbnail"]["why"]})')
    say(f'PACKED   {len(packed)} short(s) in {it.path / "clips"}')
    return 0 if packed else 1


def register(sub):
    p = sub.add_parser('assemble', help='join finished runs (a series or a list) into one long video with chapter cards')
    p.add_argument('parts', nargs='+', help='a series story id, or iterations (<name>, <name>/<n>, paths; commas or spaces)')
    p.add_argument('-o', '--output', required=True, help='the assembly\'s name: runs/<name>/<NNNN>/')
    p.add_argument('--title', action='append', help='chapter title of each part, in order (default: the story\'s title)')
    p.add_argument('--cards', default='game', choices=('game', 'plain', 'none'),
                   help='chapter cards: rendered in the game (default, one cached take), bitmap-font plain, or none')
    p.add_argument('--card-seconds', type=float, default=2.5)
    p.add_argument('--label', default='Part', help='the word under each card\'s title ("Part 2", "Episode 2")')
    p.add_argument('--cold-open', action='store_true', help='no card before the first part')
    p.add_argument('--no-measure', action='store_true')
    p.set_defaults(run=cmd_assemble)

    c = sub.add_parser('clips', help='moments for shorts, vertical 9:16 shorts (re-shot or re-framed), their titles and thumbnails')
    s = c.add_subparsers(dest='clips_command', required=True)
    f = s.add_parser('find', help='rank candidate moments (setup to payoff, 15-60 s) into clips/moments.json')
    f.add_argument('target', metavar='run', help='an iteration: <name>, <name>/<n> or a path (an assembly too)')
    f.add_argument('--min', type=float, default=15.0, help='shortest moment, seconds (default 15; a shorter master is one moment)')
    f.add_argument('--max', type=float, default=60.0)
    f.add_argument('--ask', action='store_true', help='also ask a reviewer model over the contact sheet and outline (agents.ask)')
    f.add_argument('--model')
    f.add_argument('--show', type=int, default=8)
    f.set_defaults(run=cmd_find)
    k = s.add_parser('cut', help='a vertical short of a moment or a range: re-shoot (default when the script exists) or re-frame')
    k.add_argument('target', metavar='run', help='an iteration: <name>, <name>/<n> or a path (an assembly too)')
    k.add_argument('--moment', type=int, help='a moment number from clips/moments.json')
    k.add_argument('--from', dest='start', type=float)
    k.add_argument('--to', dest='end', type=float)
    k.add_argument('--method', default='auto', choices=('auto', 'reshoot', 'reframe'))
    k.add_argument('--aspect', default='9:16')
    k.add_argument('--subject', help='re-frame: follow this actor id (or x,y,z world point) in every shot')
    k.add_argument('--hook', help='hook text in the first second (default: from the moment when it starts cold; "none" for none)')
    k.add_argument('--pull', type=float, default=1.0, help='re-shoot: pull every rig back by this factor (radius/distance)')
    k.add_argument('--timeout', type=int, default=900)
    k.set_defaults(run=cmd_cut)
    q = s.add_parser('pack', help='per short: title, description, hashtags and a thumbnail frame into clips/<n>/meta.json')
    q.add_argument('target', metavar='run', help='an iteration: <name>, <name>/<n> or a path (an assembly too)')
    q.add_argument('--ask', action='store_true', help='have a model write the titles and descriptions (agents.ask)')
    q.add_argument('--model')
    q.set_defaults(run=cmd_pack)
