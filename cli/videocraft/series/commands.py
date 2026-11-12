"""`videocraft series new <story> --episodes N` and `videocraft series status <story>` (docs/STORY.md)."""
from videocraft.series import series
from videocraft.story._ask import AskError
from videocraft.story.store import FORMATS, STAGES, Store, StoryError


def say(text=''):
    print(text, flush=True)


def cmd_new(args):
    store = Store()
    try:
        ids = series.new(store, args.story, args.episodes, from_file=args.from_file, fmt=args.format, say=say)
    except StoryError as e:
        say(f'STORY ERROR {e}')
        return 2
    except AskError as e:
        say(f'MODEL ERROR {e}')
        return 2
    for eid in ids:
        say(f'EPISODE  {eid}  {store.path(eid, "premise")}')
    say(f'NEXT     bin/videocraft story draft outline {ids[0]}   (the bible is {args.story}\'s)')
    return 0


def cmd_status(args):
    store = Store()
    try:
        record, rows = series.status(store, args.story)
    except StoryError as e:
        say(f'STORY ERROR {e}')
        return 2
    say(f'SERIES   {record["series"]}: {record["title"]}, {len(rows)} episodes')
    say(f'  {"#":>2}  {"episode":28} ' + ' '.join(f'{s:9}' for s in STAGES) + '  title')
    for n, eid, title, cells in rows:
        say(f'  {n:>2}  {eid:28} ' + ' '.join(f'{cells[s]:9}' for s in STAGES) + f'  {title}')
    return 0


def register(sub):
    p = sub.add_parser('series', help='split a story into episodes that share its bible (docs/STORY.md)')
    s = p.add_subparsers(dest='series_command', required=True)
    q = s.add_parser('new', help='split a story into N stand-alone, continuing episodes')
    q.add_argument('story')
    q.add_argument('--episodes', type=int, required=True)
    q.add_argument('--format', choices=sorted(FORMATS), help="each episode's format (default: the story's)")
    q.add_argument('--from-file', help='a hand-written split: a JSON list of episodes (docs/STORY.md)')
    q.set_defaults(run=cmd_new)
    q = s.add_parser('status', help='the episodes of a series and their stages')
    q.add_argument('story')
    q.set_defaults(run=cmd_status)
