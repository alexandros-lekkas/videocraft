package io.github.alexandroslekkas.videocraft.text;

import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.api.Params;

/**
 * {@code do = "lower_third"}: a name and a line under it at the bottom left of the safe area (or the right), on a dark
 * panel with a coloured bar, sliding in from the side; slides out again at the end of its hold.
 */
final class LowerThird extends Message {
	private final String name, role, side;
	private final int accent;
	private int k, roleK, slideOut;
	private float x0, y0, x1, y1;

	LowerThird(Params p) {
		super("lower_third", p);
		this.name = p.string("text");
		this.role = p.string("subtitle", null);
		this.side = p.string("side", "left");
		if (!side.equals("left") && !side.equals("right")) throw new IllegalArgumentException(p.where() + ": side is \"left\" or \"right\"");
		this.accent = TextLayout.color(p.string("color", "#ffe23b"), p.where() + ".color");
		double cap = p.number("size", 56);
		if (cap < TextLayout.MIN_CAP) throw new IllegalArgumentException(p.where() + ": size (the capital height) is at least " + (int) TextLayout.MIN_CAP + " px");
		this.k = TextLayout.fontScale(cap);
	}

	@Override
	void start() {
		double[] safe = layout.safe();
		// Too wide for the safe area (a vertical frame's is 896 px): step the sizes down, never below the smallest readable.
		int least = TextLayout.fontScale(TextLayout.MIN_CAP);
		float boxW, boxH;
		while (true) {
			roleK = Math.max(least, k - 2);
			float pad = 2.8f * roleK, bar = 1.8f * k;
			float w = (Ink.width(name) - 1) * k;
			if (role != null) w = Math.max(w, (Ink.width(role) - 1) * roleK);
			float h = TextLayout.CAP * k + (role != null ? 3.5f * roleK + TextLayout.CAP * roleK : 0);
			boxW = bar + pad * 2 + w;
			boxH = h + pad * 2;
			if (boxW <= safe[2] - safe[0] || k <= least) break;
			k--;
		}
		if (boxW > safe[2] - safe[0]) throw new IllegalArgumentException(params.where() + ": the lower third is wider than the safe area; shorten it");
		x0 = side.equals("left") ? (float) safe[0] : (float) safe[2] - boxW;
		x1 = x0 + boxW;
		y1 = (float) safe[3];
		y0 = y1 - boxH;
		int hold = holdEnd(startFrame);
		endFrame = hold;
		slideOut = hold == Integer.MAX_VALUE ? Integer.MAX_VALUE : hold - (int) Math.round(0.25 * shot.fps());
	}

	@Override
	int shownFrame() { return startFrame + (int) Math.round(0.35 * shot.fps()); }

	@Override
	boolean paint(Ink ink, int frame) {
		int fps = shot.fps();
		double in = TextLayout.ease((frame - startFrame + 1) / (0.35 * fps));
		if (frame >= slideOut) in = Math.min(in, 1 - TextLayout.smooth((frame - slideOut + 1) / (0.25 * fps)));
		if (in <= 0) return false;
		float travel = (x1 - x0 + 60) * (float) (1 - in) * (side.equals("left") ? -1 : 1);
		float alpha = (float) Math.min(1, in * 1.6);
		float pad = 2.8f * roleK, bar = 1.8f * k;
		float barX = side.equals("left") ? x0 : x1 - bar;
		// The panel and the bar never overlap: fills in one GUI stratum are not drawn in a guaranteed order.
		float panel0 = side.equals("left") ? x0 + bar : x0, panel1 = side.equals("left") ? x1 : x1 - bar;
		ink.box(panel0 + travel, y0, panel1 + travel, y1, Ink.fade(0xB0101418, alpha));
		ink.box(barX + travel, y0, barX + bar + travel, y1, Ink.fade(accent, alpha));
		float tx = (side.equals("left") ? x0 + bar : x0) + pad + travel;
		ink.text(name, tx, y0 + pad, k, 1, Ink.WHITE, alpha, true);
		if (role != null) ink.text(role, tx, y0 + pad + TextLayout.CAP * k + 3.5f * roleK, roleK, 1, 0xFFC9D1DC, alpha, true);
		return true;
	}

	@Override
	void describe(JsonObject o) {
		o.addProperty("text", name);
		o.addProperty("subtitle", role);
		o.addProperty("words_count", (name + (role == null ? "" : " " + role)).trim().split("\\s+").length);
		o.addProperty("side", side);
		o.addProperty("cap_height", TextLayout.CAP * k * layout.scale());
		o.addProperty("subtitle_cap_height", role == null ? null : TextLayout.CAP * roleK * layout.scale());
		o.add("box", box(layout.toFrame(x0, y0, x1, y1)));
		o.addProperty("reading_seconds", TextLayout.readingSeconds(o.get("words_count").getAsInt()));
	}
}
