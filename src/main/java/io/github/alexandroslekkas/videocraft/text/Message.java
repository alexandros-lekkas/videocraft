package io.github.alexandroslekkas.videocraft.text;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.api.Action;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.ShotContext;

/**
 * One text item on the layer: a caption, a title, a card, a lower third or a keycap. Made from its cue's parameters
 * (validated, nothing drawn) when the cue is read; laid out with the game's font on its first frame; then drawn every
 * frame until its hold runs out, the next message replaces it, a {@code clear} cue removes it or the shot ends. Each
 * one writes a record to the shot's {@code text.json} ({@link TextLog}).
 *
 * <p>Frames are shot frames: {@code frame} in {@link #paint} is the frame being drawn, which is the frame of the video.
 */
abstract class Message implements Action {
	/** Which layer slot a message takes: one message at a time, plus one keycap. */
	enum Slot { MESSAGE, KEYCAP }

	final String kind;
	final Params params;
	/** Seconds into the shot the cue asked for (the cue's own {@code at}). */
	final double cueAt;
	ShotContext shot;
	TextLayout layout;
	/** The frame the message started on, and the first frame it is no longer drawn on (exclusive); MAX_VALUE: until the cut. */
	int startFrame, endFrame = Integer.MAX_VALUE;
	private boolean started, ended;
	private String why;
	private int firstDrawn = Integer.MIN_VALUE, lastDrawn = Integer.MIN_VALUE;

	Message(String kind, Params params) {
		this.kind = kind;
		this.params = params;
		this.cueAt = params.number("at", 0);
	}

	Slot slot() { return Slot.MESSAGE; }

	/** Lays the message out (font metrics are available now). {@link #startFrame} is set. */
	abstract void start();

	/** Draws the message for {@code frame}. Returns false when nothing was visible on this frame. */
	abstract boolean paint(Ink ink, int frame);

	/** The frame on which the message is first complete (every word shown): reading time counts from here. */
	abstract int shownFrame();

	/** Kind-specific fields of the record (text, words, boxes, sizes). */
	abstract void describe(JsonObject record);

	/** Frame of a time in seconds from the start of the shot. */
	int frameAt(double seconds) { return TextLayout.frameOf(seconds, shot.fps()); }

	int now() { return TextLayout.frameOf(shot.seconds(), shot.fps()); }

	/** {@code hold} seconds after {@code from} (a frame), or MAX_VALUE when the script gives no hold. */
	int holdEnd(int from) {
		if (!params.has("hold")) return Integer.MAX_VALUE;
		double hold = params.number("hold");
		if (hold <= 0) throw new IllegalArgumentException(params.where() + ": hold is seconds > 0");
		return from + Math.max(1, (int) Math.round(hold * shot.fps()));
	}

	/** The last frame of the shot (for fades that end on the cut). */
	int lastFrame() { return (int) Math.round(shot.duration() * shot.fps()) - 1; }

	// ---- Action ----

	@Override
	public boolean frame(ShotContext shot) {
		if (!started) {
			started = true;
			this.shot = shot;
			this.layout = Ink.layout();
			startFrame = now();
			start();
			TextLayer.show(this);
		}
		if (ended) return true;
		if (now() >= endFrame) {
			end("hold");
			return true;
		}
		return false;
	}

	@Override
	public void stop(ShotContext shot) {
		if (started) end("cut");
	}

	/** Takes the message off the layer and writes its record. */
	void end(String reason) {
		if (ended) return;
		ended = true;
		why = reason;
		TextLayer.remove(this);
		TextLog.add(shot, record());
	}

	boolean ended() { return ended; }

	/** Called by the layer for each drawn frame. */
	void draw(Ink ink) {
		if (ended) return;
		int frame = now();
		if (paint(ink, frame) && shot.recording()) {
			if (firstDrawn == Integer.MIN_VALUE) firstDrawn = frame;
			lastDrawn = frame;
		}
	}

	private JsonObject record() {
		JsonObject o = new JsonObject();
		o.addProperty("kind", kind);
		o.addProperty("cue", params.where());
		o.addProperty("cue_at", cueAt);
		o.addProperty("start_frame", startFrame);
		o.addProperty("first_frame", firstDrawn == Integer.MIN_VALUE ? null : firstDrawn);
		o.addProperty("last_frame", lastDrawn == Integer.MIN_VALUE ? null : lastDrawn);
		int shown = shownFrame();
		o.addProperty("shown_frame", shown);
		int fps = shot.fps();
		o.addProperty("frames", firstDrawn == Integer.MIN_VALUE ? 0 : lastDrawn - firstDrawn + 1);
		o.addProperty("seconds", firstDrawn == Integer.MIN_VALUE ? 0 : (lastDrawn - firstDrawn + 1) / (double) fps);
		o.addProperty("complete_seconds", lastDrawn == Integer.MIN_VALUE || lastDrawn < shown ? 0 : (lastDrawn - shown + 1) / (double) fps);
		o.addProperty("ended", why);
		describe(o);
		return o;
	}

	static JsonArray box(int[] b) {
		JsonArray a = new JsonArray();
		for (int v : b) a.add(v);
		return a;
	}
}
