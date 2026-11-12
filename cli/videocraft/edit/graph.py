"""The timeline as an ffmpeg filter graph: per clip its pieces (plain, an exact nearest-neighbour hold, a smooth zoom),
then speed, the look (grade, frame) and fades; black gaps from a colour source; all joined in order.

`build(timeline, video_of, frame_png_of)` returns (inputs, graph) where inputs is the list of ffmpeg input arguments.
"""
from videocraft.edit import looks
from videocraft.edit.timeline import time_expr


def _zoom_expr(piece):
    """perspective corners for a zoom about the fixed point (fx, fy): window = f + (frame - f) / z."""
    n = piece['to'] - piece['from']
    z0, z1 = piece['z0'], piece['z1']
    if piece['kind'] == 'ramp':
        k = f'min(1,(in+1)/{n})'          # the frame before is z0, the last frame of the ramp z1
    else:
        k = f'(in/{max(1, n - 1)})'        # a slow push: first frame z0, last z1
    shape = {'linear': '{k}', 'smooth': '({k})*({k})*(3-2*({k}))', 'in': '({k})*({k})', 'out': '(1-(1-{k})*(1-{k}))'}[piece.get('ease', 'smooth')]
    e = shape.format(k=k)
    z = f'({z0!r}*pow({z1 / z0!r},{e}))' if z1 != z0 else f'{z0!r}'
    fx, fy = piece['fx'], piece['fy']
    x0, x1 = f'({fx!r}-{fx!r}/{z})', f'({fx!r}+(W-{fx!r})/{z})'
    y0, y1 = f'({fy!r}-{fy!r}/{z})', f'({fy!r}+(H-{fy!r})/{z})'
    return (f"perspective=x0='{x0}':y0='{y0}':x1='{x1}':y1='{y0}':x2='{x0}':y2='{y1}':x3='{x1}':y3='{y1}'"
            f':interpolation=cubic:sense=source:eval=frame')


def piece_chain(piece, width, height):
    kind = piece['kind']
    if kind == 'plain':
        return ''
    if kind == 'hold':
        cw, ch, left, top = piece['window']
        # The exact crop scaled with nearest neighbour: the game's pixel font stays crisp.
        return f'crop={cw}:{ch}:{left}:{top},scale={width}:{height}:flags=neighbor'
    return _zoom_expr(piece)


def build(timeline, video_of, frame_png_of):
    fps, width, height = timeline['fps'], timeline['width'], timeline['height']
    inputs, graph, labels = [], [], []

    def add_input(args):
        inputs.extend(args)
        return sum(1 for a in inputs if a == '-i') - 1

    for clip in timeline['clips']:
        i, n = clip['index'], clip['out_frames']
        if clip['kind'] == 'black':
            graph.append(f'color=c=black:s={width}x{height}:r={fps},trim=end_frame={n},setsar=1,format=yuv420p[v{i}]')
            labels.append(f'[v{i}]')
            continue
        src = add_input(['-i', str(video_of(clip['shot']))])
        pieces = clip['push']
        chains = []
        for piece in pieces:
            chain = f'trim=start_frame={piece["from"]}:end_frame={piece["to"]},setpts=PTS-STARTPTS'
            extra = piece_chain(piece, width, height)
            chains.append(chain + (',' + extra if extra else '') + ',setsar=1,format=yuv420p')
        if len(chains) == 1:
            graph.append(f'[{src}:v]{chains[0]}[c{i}]')
        else:
            graph.append(f'[{src}:v]split={len(chains)}' + ''.join(f'[s{i}_{j}]' for j in range(len(chains))))
            for j, chain in enumerate(chains):
                graph.append(f'[s{i}_{j}]{chain}[p{i}_{j}]')
            graph.append(''.join(f'[p{i}_{j}]' for j in range(len(chains))) + f'concat=n={len(chains)}:v=1:a=0[c{i}]')
        post = []
        if clip.get('speed_keys'):
            expr = time_expr([tuple(k) for k in clip['speed_keys']], clip['src_in'])
            # Each source frame gets its output slot; fps repeats or drops to fill the slots; the count is made exact.
            post += [f"setpts='floor({expr}+0.5)/({fps}*TB)'", f'fps={fps}', 'tpad=stop_mode=clone:stop=8', f'trim=end_frame={n}']
        look = clip.get('look') or {}
        grade = looks.grade_filter(look.get('grade'))
        if grade:
            post.append(grade)
        label = f'c{i}'
        if post:
            graph.append(f'[{label}]' + ','.join(post) + f'[g{i}]')
            label = f'g{i}'
        if look.get('frame') is not None:
            png = add_input(['-loop', '1', '-framerate', str(fps), '-i', str(frame_png_of(look['frame']))])
            graph.append(f'[{png}:v]format=rgba,scale=out_color_matrix=bt709:out_range=tv,format=yuva420p[o{i}]')
            graph.append(f'[{label}][o{i}]overlay=0:0:shortest=1:eof_action=endall:format=yuv420[f{i}]')
            label = f'f{i}'
        fades = []
        if clip['fade_in']:
            fades.append(f'fade=t=in:s=0:n={clip["fade_in"]}')
        if clip['fade_out']:
            fades.append(f'fade=t=out:s={n - clip["fade_out"]}:n={clip["fade_out"]}')
        graph.append(f'[{label}]' + ','.join(fades + ['setsar=1', 'format=yuv420p']) + f'[v{i}]')
        labels.append(f'[v{i}]')
    # One clean constant-rate timeline: frame N of the cut at N / fps.
    graph.append(''.join(labels) + f'concat=n={len(labels)}:v=1:a=0,setpts=N/({fps}*TB)[v]')
    return inputs, graph

