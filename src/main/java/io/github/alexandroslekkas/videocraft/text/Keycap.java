package io.github.alexandroslekkas.videocraft.text;

import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.api.Params;

/**
 * {@code do = "keycap"}: a keyboard key that pops in, goes down (yellow) when it is pressed and fades a moment later; it
 * shows a key press the viewer cannot see. It has its own slot, so it can sit with a caption that explains it.
 */
final class Keycap extends Message {
	private final String key;
	private final double press, after;
	private final double x, y;
	private final int k;
	private int pressFrame;
	private float half;

	Keycap(Params p) {
		super("keycap", p);
		this.key = p.string("key");
		this.press = p.number("press", 0.5);
		this.after = p.number("hold", 0.7);
		this.x = p.number("x", Double.NaN);
		this.y = p.number("y", Double.NaN);
		double cap = p.number("size", 56);
		if (cap < TextLayout.MIN_CAP) throw new IllegalArgumentException(p.where() + ": size (the capital height of the label) is at least " + (int) TextLayout.MIN_CAP + " px");
		this.k = TextLayout.fontScale(cap);
		if (press < 0 || after <= 0) throw new IllegalArgumentException(p.where() + ": press (seconds after the cue) >= 0 and hold (seconds after the press) > 0");
	}

	@Override
	Slot slot() { return Slot.KEYCAP; }

	@Override
	void start() {
		pressFrame = startFrame + (int) Math.round(press * shot.fps());
		endFrame = pressFrame + (int) Math.round((after + 0.25) * shot.fps());
		half = Math.max(8, (Ink.width(key) - 1) / 2f + 5);
	}

	private float cx() { return (float) (Double.isNaN(x) ? layout.width() / 2 : x); }

	private float cy() { return (float) (Double.isNaN(y) ? layout.height() * 0.62 : y); }

	@Override
	int shownFrame() { return startFrame; }

	@Override
	boolean paint(Ink ink, int frame) {
		int fps = shot.fps();
		float scale = TextLayout.pop(frame - startFrame, fps);
		float alpha = (float) Math.max(0, Math.min(1, 1 - (frame - pressFrame - after * fps) / (0.25 * fps)));
		if (scale <= 0 || alpha <= 0) return false;
		boolean down = frame >= pressFrame && frame < pressFrame + 0.16 * fps;
		// Pressing it is a second, smaller pop.
		if (frame >= pressFrame) scale *= 1 + 0.1f * (float) Math.max(0, 1 - (frame - pressFrame) / (0.22 * fps));
		// The key is 17 font pixels tall at a label of 7: dark rim, a lip below the face that the press pushes in.
		float u = k * scale, cx = cx(), cy = cy(), drop = down ? u : 0;
		ink.box(cx - half * u, cy - 8 * u + drop, cx + half * u, cy + 9 * u, Ink.fade(Ink.INK, alpha));
		ink.box(cx - (half - 1) * u, cy - 7 * u + drop, cx + (half - 1) * u, cy + 8 * u, Ink.fade(0xFF8E96A3, alpha));
		ink.box(cx - (half - 1) * u, cy - 7 * u + drop, cx + (half - 1) * u, cy + 5 * u + drop, Ink.fade(down ? Ink.YELLOW : 0xFFF2F4F7, alpha));
		float w = Ink.width(key) * u;
		ink.text(key, cx - w / 2 + u / 2, cy - 5 * u + drop, u, 1, Ink.INK, alpha, false);
		return true;
	}

	@Override
	void describe(JsonObject o) {
		o.addProperty("text", key);
		o.addProperty("words_count", 1);
		o.addProperty("press_frame", pressFrame);
		o.addProperty("cap_height", TextLayout.CAP * k * layout.scale());
		float cx = cx(), cy = cy();
		o.add("box", box(layout.toFrame(cx - half * k, cy - 8 * k, cx + half * k, cy + 9 * k)));
	}
}
