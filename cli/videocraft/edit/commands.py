"""`videocraft edit ...`: the picture edit's own commands (the plain `videocraft cut <run>` stays the quick way)."""
import json


def _cut(args):
    from videocraft import store
    from videocraft.edit.cut import cut
    print(cut(store.open_iteration(args.iteration), silent=True if args.silent else None, exports=not args.no_exports,
              original_audio=args.original_audio))
    return 0


def _timeline(args):
    from videocraft import store
    from videocraft.edit.cut import timeline_of
    print(json.dumps(timeline_of(store.open_iteration(args.iteration)), indent=1))
    return 0


def _verify(args):
    from videocraft import store
    from videocraft.edit.verify import verify
    report = verify(store.open_iteration(args.iteration))
    for clip in report['clips']:
        for check in clip['checks']:
            print(f'{"PASS" if check["pass"] else "FAIL"}  clip {clip["index"]:2} {clip["kind"]:5} {clip["shot"] or "":12} '
                  f'{clip["out_frames"]:4} frames  {check["what"]}  out {check.get("out", "")}')
    print(f'{"PASS" if report["pass"] else "FAIL"}  {report["frames"]} frames rendered, {report["expected_frames"]} in the timeline')
    return 0 if report['pass'] else 1


def register(sub):
    p = sub.add_parser('edit', help='the picture edit: cut (with --silent), timeline, verify')
    s = p.add_subparsers(dest='edit_command', required=True)
    c = s.add_parser('cut', help='cut an iteration again (the latest of a script, name/3, or a path)')
    c.add_argument('iteration')
    c.add_argument('--silent', action='store_true', help='no sound track (also VIDEOCRAFT_SILENT=1 or [edit] audio = "none")')
    c.add_argument('--no-exports', action='store_true', help='the master and poster only')
    c.add_argument('--original-audio', action='store_true', help='also <export>-original-audio.mp4 (and master-original-audio.mp4) '
                   'with a sound track that holds no game audio, cut/audio-original.wav')
    c.set_defaults(run=_cut)
    t = s.add_parser('timeline', help='print the resolved timeline (frames of every clip) without encoding')
    t.add_argument('iteration')
    t.set_defaults(run=_timeline)
    v = s.add_parser('verify', help='prove clips are exact to the frame and push-in holds pixel-exact (writes cut/verify.json)')
    v.add_argument('iteration')
    v.set_defaults(run=_verify)
