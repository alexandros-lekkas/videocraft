# A cold read: does this film make sense?

You are watching a short comedy video for the first time. You have never seen its premise, notes or outline: all
you get is what reaches the screen, written down below in the order the film plays it: each shot's name and camera,
what is seen (a short picture note, then the action cues: who walks, turns, jumps, sleeps), what is heard (sound
effects), the text shown on screen, and every spoken line as `Name [id]: line`. The name is the speaker tag the
viewer sees on the caption and the voice they hear; the `[id]` is only there so your fixes can point at the right
character. A line marked "cut to the next shot on X" carries over the cut: its words from X on are heard over the
next shot. `[black]` is a moment of black between shots.

Read it as that viewer, line by line, and say where it stops making sense. Look for:

- **nonsense**: a line a viewer cannot follow, or that contradicts what was just seen or said;
- **missing_setup**: a joke, callback or reveal whose setup never came (or came after it), a name or object used as if
  the viewer already knew it;
- **name**: one character called by two names (in the lines, the captions or the speaker tags), or two characters
  sharing one name, or a speaker who is never introduced but is talked about as known;
- **split_sentence**: a sentence broken across shots or speakers so that it reads wrong in pieces;
- **non_sequitur**: a line that does not follow from the one before it, unless the jump is the joke and lands;
- **joke**: a joke that does not land for a cold viewer (explain why; not a matter of taste);
- **unclear_picture**: a line that only makes sense with a picture the cues do not show;
- **other**.

Score how well it makes sense to a first-time viewer, 1 to 10: 10 every line and beat lands; 8 a viewer follows the
whole story and gets every joke, with at most small rough spots; 5 the gist is clear but several lines lose them; 2
it does not hold together. A film needs {{passing}} to be filmed. Be strict and concrete: every issue quotes the line
exactly as written below, names its shot, and gives a fix that can be pasted in (the rewritten line, or exactly what
to add and where). Keep fixes short: lines are spoken at about three words a second in shots of a few seconds. Do
not suggest new shots, sets or characters unless nothing else can fix it. Do not list issues of taste, pacing or
style that do not stop the film making sense.

## The film

{{transcript}}

## Your answer

JSON only, matching the schema you are given: `score` (1-10), `understood` (what you think happens and why it is
funny, in 2-4 sentences: this is how the writer learns what came across), and `issues` (most serious first).
