package io.github.alexandroslekkas.videocraft.text;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.api.Params;

import java.util.ArrayList;
import java.util.List;

/**
 * {@code do = "caption"}: words that pop in one after another (or at explicit times from a voice timeline), white in
 * the game's font with a dark outline, the {@code *key} word yellow and breathing, at most two lines inside the safe
 * area, an optional coloured speaker tag above. Stays until its hold runs out, the next message or the cut.
 */
final class Caption extends Message {
	/** Default seconds between words popping in. */
	static final double STAGGER = 0.12;
	static final double DEFAULT_CAP = 63, TAG_CAP = 42;

	private record Word(String text, boolean key, boolean breakBefore, double at) {}

	private final List<Word> words = new ArrayList<>();
	private final boolean whole, shade;
	private final String position, speaker;
	private final int color, keyColor, speakerColor;
	private final double stagger, cap;
	// Laid out in start():
	private int k, tagK;
	private int[] wordFrames;
	private float[] wordX, wordY;
	private float tagX0, tagY0, tagX1, tagY1, boxX0, boxY0, boxX1, boxY1;
	private List<List<Integer>> lines;

	Caption(Params p) {
		super("caption", p);
		String where = p.where();
		this.whole = switch (p.string("style", "pop")) {
			case "pop" -> false;
			case "whole" -> true;
			default -> throw new IllegalArgumentException(where + ": style is \"pop\" (words pop in) or \"whole\" (all at once, no animation)");
		};
		this.position = p.string("position", "bottom");
		if (!List.of("bottom", "top", "center").contains(position))
			throw new IllegalArgumentException(where + ": position is \"bottom\", \"top\" or \"center\"");
		this.stagger = p.number("stagger", STAGGER);
		this.cap = p.number("size", DEFAULT_CAP);
		if (cap < TextLayout.MIN_CAP) throw new IllegalArgumentException(where + ": size (the capital height) is at least " + (int) TextLayout.MIN_CAP + " px, or it does not read on a phone");
		this.color = TextLayout.color(p.string("color", "#ffffff"), where + ".color");
		this.keyColor = TextLayout.color(p.string("key_color", "#ffe23b"), where + ".key_color");
		this.shade = p.bool("shade", false);
		JsonElement s = p.raw("speaker");
		if (s != null && s.isJsonObject()) {
			Params sp = p.child("speaker");
			this.speaker = sp.string("name");
			this.speakerColor = TextLayout.color(sp.string("color", "#5aa9e6"), where + ".speaker.color");
		} else {
			this.speaker = s == null || s.isJsonNull() ? null : s.getAsString();
			this.speakerColor = TextLayout.color(p.string("speaker_color", "#5aa9e6"), where + ".speaker_color");
		}
		if (p.has("words")) {
			for (JsonElement e : p.json().getAsJsonArray("words")) {
				if (!e.isJsonObject() || !e.getAsJsonObject().has("w"))
					throw new IllegalArgumentException(where + ": words = [{ w = \"Hey.\", at = 0.0 }, ...] (seconds from the cue)");
				JsonObject w = e.getAsJsonObject();
				double at = w.has("at") ? w.get("at").getAsDouble() : Double.NaN;
				boolean br = w.has("br") && w.get("br").getAsBoolean();
				add(w.get("w").getAsString(), br, at, where);
			}
		} else {
			JsonElement t = p.raw("text");
			if (t == null || t.isJsonNull()) throw new IllegalArgumentException(where + ": a caption needs text = \"...\" (or a list of lines) or words = [...]");
			List<String> given = new ArrayList<>();
			if (t.isJsonArray()) for (JsonElement e : t.getAsJsonArray()) given.add(e.getAsString());
			else given.add(t.getAsString());
			for (int line = 0; line < given.size(); line++) {
				boolean first = true;
				for (String w : given.get(line).trim().split("\\s+")) {
					if (w.isEmpty()) continue;
					// A list of lines asks for those line breaks; a single string is wrapped to fit.
					add(w, t.isJsonArray() && first && line > 0, Double.NaN, where);
					first = false;
				}
			}
		}
		if (words.isEmpty()) throw new IllegalArgumentException(where + ": the caption has no words");
		double last = -1;
		for (Word w : words) {
			if (Double.isNaN(w.at())) continue;
			if (w.at() < last) throw new IllegalArgumentException(where + ": word times must not go backwards (\"" + w.text() + "\" at " + w.at() + ")");
			last = w.at();
		}
	}

	private void add(String raw, boolean br, double at, String where) {
		boolean key = raw.startsWith("*") && raw.length() > 1;
		String text = key ? raw.substring(1) : raw;
		if (text.isBlank()) throw new IllegalArgumentException(where + ": an empty word");
		words.add(new Word(text, key, br, at));
	}

	@Override
	void start() {
		List<String> texts = words.stream().map(Word::text).toList();
		List<Integer> forced = new ArrayList<>();
		for (int i = 0; i < words.size(); i++) if (words.get(i).breakBefore()) forced.add(i);
		double[] safe = layout.safe();
		int space = Ink.width(" ");
		int largest = TextLayout.fontScale(cap), smallest = Math.max(TextLayout.fontScale(TextLayout.MIN_CAP), Math.min(largest, 7));
		TextLayout.Fit fit = TextLayout.fit(texts, Ink::width, space, safe[2] - safe[0], 2, largest, smallest, false, forced);
		if (fit == null) {
			throw new IllegalArgumentException(params.where() + ": the caption does not fit on two lines inside the safe area ("
				+ (int) (safe[2] - safe[0]) + " layout px wide) even at the smallest readable size; shorten it or split it into two captions");
		}
		k = fit.fontScale();
		lines = fit.lines();
		float lineHeight = TextLayout.LINE * k, capH = TextLayout.CAP * k;
		float blockH = (lines.size() - 1) * lineHeight + capH;
		float top = switch (position) {
			case "top" -> (float) safe[1] + 0.9f * k + (speaker != null ? tagHeight() : 0);
			case "center" -> (float) (layout.height() - blockH) / 2;
			default -> (float) safe[3] - 1.6f * k - blockH;
		};
		wordX = new float[words.size()];
		wordY = new float[words.size()];
		boxX0 = Float.MAX_VALUE;
		boxX1 = -Float.MAX_VALUE;
		for (int l = 0; l < lines.size(); l++) {
			List<Integer> line = lines.get(l);
			float width = TextLayout.lineWidth(texts, line, Ink::width, space) * k;
			// Whole layout pixels keep the font's pixels on whole frame pixels at a 1080-line frame.
			float x = Math.round((float) layout.centreX() - width / 2);
			float y = Math.round(top + l * lineHeight);
			boxX0 = Math.min(boxX0, x);
			boxX1 = Math.max(boxX1, x + width - k);
			for (int i : line) {
				wordX[i] = x;
				wordY[i] = y;
				x += (Ink.width(texts.get(i)) + space) * k;
			}
		}
		boxY0 = Math.round(top);
		boxY1 = Math.round(top + blockH + k);   // the descenders
		if (speaker != null) {
			tagK = Math.max(5, Math.min(k - 2, TextLayout.fontScale(TAG_CAP)));
			float w = (Ink.width(speaker) - 1) * tagK, pad = 1.5f * tagK;
			tagX1 = Math.round((float) layout.centreX() + w / 2 + pad);
			tagX0 = Math.round((float) layout.centreX() - w / 2 - pad);
			tagY1 = Math.round(boxY0 - 0.9f * k);
			tagY0 = Math.round(tagY1 - TextLayout.CAP * tagK - 2 * 1.1f * tagK);
		}
		// When each word pops: explicit times from the cue, else a stagger from the cue's own frame.
		wordFrames = new int[words.size()];
		double next = startFrame / (double) shot.fps();
		for (int i = 0; i < words.size(); i++) {
			Word w = words.get(i);
			int f;
			if (whole) f = startFrame;
			else if (!Double.isNaN(w.at())) {
				// The frame nearest the given time: this is where a voice timeline puts the word, exactly.
				f = frameAt(cueAt + w.at());
				next = cueAt + w.at() + stagger;
			} else {
				f = frameAt(next);
				if (i > 0) f = Math.max(f, wordFrames[i - 1] + 1);
				next += stagger;
			}
			wordFrames[i] = Math.max(startFrame, f);
		}
		endFrame = holdEnd(shownFrame());
	}

	private float tagHeight() { return (TextLayout.CAP + 2.2f) * Math.max(5, TextLayout.fontScale(TAG_CAP)) + 0.9f * TextLayout.fontScale(cap); }

	@Override
	int shownFrame() { return wordFrames[wordFrames.length - 1]; }

	@Override
	boolean paint(Ink ink, int frame) {
		if (frame < wordFrames[0]) return false;
		int fps = shot.fps();
		// A short fade at the end of a hold; replaced or cut, it simply goes with the cut.
		float out = endFrame == Integer.MAX_VALUE ? 1 : (float) Math.min(1, (endFrame - frame) / 5.0);
		if (shade) {
			float alpha = (float) Math.min(1, (frame - wordFrames[0] + 1) / 12.0) * out;
			float y0 = boxY0 - 3 * k - (speaker != null ? tagY1 - tagY0 + k : 0);
			if (position.equals("bottom")) ink.gradient(0, y0, (float) layout.width(), (float) layout.height(), 0, Ink.fade(0x8C000000, alpha));
			else if (position.equals("top")) ink.gradient(0, 0, (float) layout.width(), boxY1 + 3 * k, Ink.fade(0x8C000000, alpha), 0);
			else ink.box(0, boxY0 - 2 * k, (float) layout.width(), boxY1 + 2 * k, Ink.fade(0x66000000, alpha));
		}
		if (speaker != null) {
			int age = frame - wordFrames[0];
			float pop = whole ? 1 : TextLayout.pop(age, fps), alpha = (whole ? 1 : TextLayout.popAlpha(age, fps)) * out;
			float cx = (tagX0 + tagX1) / 2, cy = (tagY0 + tagY1) / 2, hw = (tagX1 - tagX0) / 2 * pop, hh = (tagY1 - tagY0) / 2 * pop;
			ink.pill(cx - hw - tagK * 0.7f, cy - hh - tagK * 0.7f, cx + hw + tagK * 0.7f, cy + hh + tagK * 0.7f, tagK, Ink.fade(Ink.INK, alpha));
			ink.pill(cx - hw, cy - hh, cx + hw, cy + hh, tagK, Ink.fade(speakerColor, alpha));
			float w = Ink.width(speaker) * tagK;
			ink.text(speaker, cx - w / 2 + tagK * 0.5f, cy - TextLayout.CAP * tagK / 2f, tagK, pop, Ink.on(speakerColor), alpha, false);
		}
		for (int i = 0; i < words.size(); i++) {
			int age = frame - wordFrames[i];
			if (age < 0) continue;
			Word w = words.get(i);
			float pop = whole ? 1 : TextLayout.pop(age, fps), alpha = (whole ? 1 : TextLayout.popAlpha(age, fps)) * out;
			// The key word breathes after it lands, like the splash on the title screen.
			if (w.key() && !whole && age >= TextLayout.POP * fps) pop *= 1 + 0.045f * (float) Math.abs(Math.sin((age - TextLayout.POP * fps) / fps * Math.PI * 1.6));
			ink.text(w.text(), wordX[i], wordY[i], k, pop, w.key() ? keyColor : color, alpha, true);
		}
		return true;
	}

	@Override
	void describe(JsonObject o) {
		StringBuilder text = new StringBuilder();
		JsonArray ls = new JsonArray(), ws = new JsonArray();
		for (List<Integer> line : lines) {
			StringBuilder l = new StringBuilder();
			for (int i : line) l.append(l.isEmpty() ? "" : " ").append(words.get(i).text());
			ls.add(l.toString());
			text.append(text.isEmpty() ? "" : " ").append(l);
		}
		for (int l = 0; l < lines.size(); l++) {
			for (int i : lines.get(l)) {
				Word w = words.get(i);
				JsonObject j = new JsonObject();
				j.addProperty("w", w.text());
				j.addProperty("key", w.key());
				j.addProperty("line", l);
				j.addProperty("frame", wordFrames[i]);
				float x0 = wordX[i], x1 = wordX[i] + (Ink.width(w.text()) - 1) * k;
				j.add("box", box(layout.toFrame(x0, wordY[i], x1, wordY[i] + TextLayout.CAP * k)));
				ws.add(j);
			}
		}
		o.addProperty("text", text.toString());
		o.add("lines", ls);
		o.addProperty("words_count", words.size());
		o.addProperty("style", whole ? "whole" : "pop");
		o.addProperty("position", position);
		o.addProperty("speaker", speaker);
		o.addProperty("cap_height", TextLayout.CAP * k * layout.scale());
		o.add("box", box(layout.toFrame(boxX0, boxY0, boxX1, boxY1)));
		if (speaker != null) {
			o.add("tag_box", box(layout.toFrame(tagX0, tagY0, tagX1, tagY1)));
			o.addProperty("tag_cap_height", TextLayout.CAP * tagK * layout.scale());
		}
		o.add("words", ws);
		o.addProperty("reading_seconds", TextLayout.readingSeconds(words.size()));
	}
}
