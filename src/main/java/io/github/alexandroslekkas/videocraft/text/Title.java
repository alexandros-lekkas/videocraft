package io.github.alexandroslekkas.videocraft.text;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.api.Params;

import java.util.ArrayList;
import java.util.List;

/**
 * {@code do = "title"}: big centred words over the picture, with depth and an outline; and {@code do = "card"}: the same
 * over a full-frame background (black by default, opaque or see-through) that can fade in and out, for end cards and
 * graphic inserts. Both take a small subtitle under the title. Letters can drop in one after another ({@code style =
 * "drop"}), words pop ({@code "pop"}), or everything is there on the first frame ({@code "whole"}).
 */
final class Title extends Message {
	static final double TITLE_CAP = 112, SUBTITLE_CAP = 56;

	private final boolean card;
	private final String style, position;
	private final List<String> titleWords = new ArrayList<>(), subWords = new ArrayList<>();
	private final List<Boolean> titleKeys = new ArrayList<>();
	private final List<Integer> titleBreaks = new ArrayList<>(), subBreaks = new ArrayList<>();
	private final int titleColor, subColor, keyColor, background;
	private final double titleCap, subCap, fadeIn, fadeOut;
	private final float shade;
	// Laid out in start():
	private TextLayout.Fit titleFit, subFit;
	private float[] titleX, titleY, subX, subY;
	private float boxX0, boxY0, boxX1, boxY1;
	private int[] wordFrames;
	private int subFrame, fadeOutFrom;

	Title(String kind, Params p) {
		super(kind, p);
		String where = p.where();
		this.card = kind.equals("card");
		this.style = p.string("style", card ? "whole" : "pop");
		if (!List.of("drop", "pop", "whole").contains(style))
			throw new IllegalArgumentException(where + ": style is \"drop\" (letters drop in), \"pop\" (words pop in) or \"whole\"");
		this.position = p.string("position", "center");
		if (!List.of("bottom", "top", "center").contains(position))
			throw new IllegalArgumentException(where + ": position is \"center\", \"top\" or \"bottom\"");
		words(p, card ? "title" : "text", titleWords, titleKeys, titleBreaks, !card);
		words(p, "subtitle", subWords, null, subBreaks, false);
		if (titleWords.isEmpty() && subWords.isEmpty())
			throw new IllegalArgumentException(where + ": a " + kind + " needs " + (card ? "title" : "text") + " = \"...\" (and may have subtitle = \"...\")");
		this.titleCap = p.number("size", TITLE_CAP);
		this.subCap = p.number("subtitle_size", SUBTITLE_CAP);
		if (titleCap < TextLayout.MIN_CAP || subCap < TextLayout.MIN_CAP)
			throw new IllegalArgumentException(where + ": sizes (capital heights) are at least " + (int) TextLayout.MIN_CAP + " px");
		this.titleColor = TextLayout.color(p.string("color", "#ffffff"), where + ".color");
		this.subColor = TextLayout.color(p.string("subtitle_color", card ? "#c9d1dc" : "#ffffff"), where + ".subtitle_color");
		this.keyColor = TextLayout.color(p.string("key_color", "#ffe23b"), where + ".key_color");
		int bg = TextLayout.color(p.string("background", "#000000"), where + ".background");
		double opacity = p.number("opacity", 1.0);
		if (opacity < 0 || opacity > 1) throw new IllegalArgumentException(where + ": opacity is 0 to 1");
		this.background = card ? Ink.fade(bg, (float) opacity) : 0;
		this.fadeIn = p.number("fade_in", 0);
		this.fadeOut = p.number("fade_out", 0);
		if (fadeIn < 0 || fadeOut < 0) throw new IllegalArgumentException(where + ": fade_in and fade_out are seconds >= 0");
		JsonElement s = p.raw("shade");
		this.shade = s == null || s.isJsonNull() ? 0 : s.getAsJsonPrimitive().isBoolean() ? (s.getAsBoolean() ? 0.55f : 0) : s.getAsFloat();
	}

	/** Reads a string or a list of lines into words; {@code *word} is a key word when {@code keys} is given. */
	private static void words(Params p, String key, List<String> out, List<Boolean> keys, List<Integer> breaks, boolean required) {
		JsonElement t = p.raw(key);
		if (t == null || t.isJsonNull()) {
			if (required) throw new IllegalArgumentException(p.where() + ": missing '" + key + "'");
			return;
		}
		List<String> lines = new ArrayList<>();
		if (t.isJsonArray()) for (JsonElement e : t.getAsJsonArray()) lines.add(e.getAsString());
		else lines.add(t.getAsString());
		for (int l = 0; l < lines.size(); l++) {
			boolean first = true;
			for (String w : lines.get(l).trim().split("\\s+")) {
				if (w.isEmpty()) continue;
				boolean isKey = keys != null && w.startsWith("*") && w.length() > 1;
				if (first && l > 0 && t.isJsonArray()) breaks.add(out.size());
				out.add(isKey ? w.substring(1) : w);
				if (keys != null) keys.add(isKey);
				first = false;
			}
		}
	}

	@Override
	void start() {
		double[] safe = layout.safe();
		double width = safe[2] - safe[0];
		int space = Ink.width(" ");
		float gap = 0;
		float titleH = 0, subH = 0;
		if (!titleWords.isEmpty()) {
			int largest = TextLayout.fontScale(titleCap);
			titleFit = TextLayout.fit(titleWords, Ink::width, space, width, 2, largest, Math.min(largest, TextLayout.MIN_SCALE), true, titleBreaks);
			if (titleFit == null) throw new IllegalArgumentException(params.where() + ": the title does not fit on two lines inside the safe area; shorten it");
			titleH = (titleFit.lineCount() - 1) * TextLayout.LINE * titleFit.fontScale() + TextLayout.CAP * titleFit.fontScale();
		}
		if (!subWords.isEmpty()) {
			int largest = TextLayout.fontScale(subCap);
			subFit = TextLayout.fit(subWords, Ink::width, space, width, 2, largest, Math.min(largest, TextLayout.MIN_SCALE), false, subBreaks);
			if (subFit == null) throw new IllegalArgumentException(params.where() + ": the subtitle does not fit on two lines inside the safe area; shorten it");
			subH = (subFit.lineCount() - 1) * TextLayout.LINE * subFit.fontScale() + TextLayout.CAP * subFit.fontScale();
			if (titleFit != null) gap = 4.5f * subFit.fontScale();
		}
		float blockH = titleH + gap + subH;
		float top = switch (position) {
			case "top" -> (float) safe[1] + 20;
			case "bottom" -> (float) safe[3] - 20 - blockH;
			default -> (float) (layout.height() * (card ? 0.5 : 0.47) - blockH / 2);
		};
		boxY0 = Math.round(top);
		boxY1 = Math.round(top + blockH + (subFit != null ? subFit.fontScale() : titleFit.fontScale()));
		boxX0 = Float.MAX_VALUE;
		boxX1 = -Float.MAX_VALUE;
		if (titleFit != null) {
			float[][] xy = place(titleWords, titleFit, top);
			titleX = xy[0];
			titleY = xy[1];
		}
		if (subFit != null) {
			float[][] xy = place(subWords, subFit, top + titleH + gap);
			subX = xy[0];
			subY = xy[1];
		}
		// Timing: words or letters in, then the subtitle 0.1 s after the title has landed.
		int fps = shot.fps();
		wordFrames = new int[titleWords.size()];
		int fadeFrames = (int) Math.round(fadeIn * fps);
		int landed = startFrame + fadeFrames / 2;
		for (int i = 0; i < titleWords.size(); i++) {
			wordFrames[i] = switch (style) {
				case "pop" -> startFrame + fadeFrames / 2 + (int) Math.round(i * 0.1 * fps);
				case "drop" -> startFrame + fadeFrames / 2 + (int) Math.round(letterIndex(i) * 0.05 * fps);
				default -> startFrame;
			};
			int done = wordFrames[i] + switch (style) {
				case "pop" -> (int) Math.round(TextLayout.POP * fps);
				case "drop" -> (int) Math.round((titleWords.get(i).length() - 1) * 0.05 * fps + 0.38 * fps);
				default -> 0;
			};
			landed = Math.max(landed, done);
		}
		subFrame = style.equals("whole") ? startFrame + fadeFrames : landed + (titleWords.isEmpty() ? 0 : (int) Math.round(0.1 * fps));
		int hold = holdEnd(startFrame);
		endFrame = hold;
		int end = hold == Integer.MAX_VALUE ? lastFrame() + 1 : hold;
		fadeOutFrom = end - (int) Math.round(fadeOut * fps);
	}

	/** Index of the first letter of word i in the whole title (letters drop one after another across words). */
	private int letterIndex(int word) {
		int n = 0;
		for (int i = 0; i < word; i++) n += titleWords.get(i).length() + 1;
		return n;
	}

	private float[][] place(List<String> words, TextLayout.Fit fit, float top) {
		int k = fit.fontScale(), space = Ink.width(" ");
		float[] xs = new float[words.size()], ys = new float[words.size()];
		for (int l = 0; l < fit.lineCount(); l++) {
			List<Integer> line = fit.lines().get(l);
			float w = TextLayout.lineWidth(words, line, Ink::width, space) * k;
			float x = Math.round((float) layout.centreX() - w / 2), y = Math.round(top + l * TextLayout.LINE * k);
			boxX0 = Math.min(boxX0, x);
			boxX1 = Math.max(boxX1, x + w - k);
			for (int i : line) {
				xs[i] = x;
				ys[i] = y;
				x += (Ink.width(words.get(i)) + space) * k;
			}
		}
		return new float[][] {xs, ys};
	}

	@Override
	int shownFrame() {
		int fps = shot.fps();
		return subFit != null ? subFrame + (style.equals("whole") ? 0 : (int) Math.round(0.3 * fps)) : Math.max(startFrame + (int) Math.round(fadeIn * fps), wordFrames.length == 0 ? startFrame : landedFrame());
	}

	private int landedFrame() {
		int fps = shot.fps(), out = startFrame;
		for (int i = 0; i < wordFrames.length; i++) {
			out = Math.max(out, wordFrames[i] + switch (style) {
				case "pop" -> (int) Math.round(TextLayout.POP * fps) - 1;
				case "drop" -> (int) Math.round((titleWords.get(i).length() - 1) * 0.05 * fps + 0.38 * fps) - 1;
				default -> 0;
			});
		}
		return out;
	}

	@Override
	boolean paint(Ink ink, int frame) {
		int fps = shot.fps();
		float alpha = 1;
		if (fadeIn > 0) alpha = (float) Math.min(1, (frame - startFrame + 1) / (fadeIn * fps));
		if (frame >= fadeOutFrom && fadeOut > 0) alpha = Math.min(alpha, (float) Math.max(0, (fadeOutFrom + fadeOut * fps - frame - 1) / (fadeOut * fps)));
		if (alpha <= 0) return false;
		if (card) ink.box(0, 0, (float) layout.width(), (float) layout.height(), Ink.fade(background, alpha));
		if (shade > 0) {
			float pad = 160;
			float a = shade * alpha;
			ink.gradient(0, boxY0 - pad, (float) layout.width(), (boxY0 + boxY1) / 2f, 0, Ink.fade(0xFF000000, a));
			ink.gradient(0, (boxY0 + boxY1) / 2f, (float) layout.width(), boxY1 + pad, Ink.fade(0xFF000000, a), 0);
		}
		if (titleFit != null) {
			int k = titleFit.fontScale();
			for (int i = 0; i < titleWords.size(); i++) {
				String word = titleWords.get(i);
				int rgb = titleKeys.get(i) ? keyColor : titleColor;
				int age = frame - wordFrames[i];
				switch (style) {
					case "pop" -> {
						if (age >= 0) ink.deep(word, titleX[i], titleY[i], k, TextLayout.pop(age, fps), rgb, alpha * TextLayout.popAlpha(age, fps));
					}
					case "drop" -> {
						float x = titleX[i];
						for (int c = 0; c < word.length(); c++) {
							String letter = word.substring(c, c + 1);
							double t = (age - c * 0.05 * fps) / (0.38 * fps);
							if (t >= 0) {
								// Falls from above the frame and bounces once.
								float fall = t >= 1 ? 0 : (float) (t < 0.62 ? -420 * (1 - TextLayout.ease(t / 0.62) * TextLayout.ease(t / 0.62)) : -0.4 * k * 7 * Math.sin((t - 0.62) / 0.38 * Math.PI));
								ink.deep(letter, x, titleY[i] + fall, k, 1, rgb, alpha);
							}
							x += Ink.width(letter) * k;
						}
					}
					default -> ink.deep(word, titleX[i], titleY[i], k, 1, rgb, alpha);
				}
			}
		}
		if (subFit != null) {
			int k = subFit.fontScale();
			float in = style.equals("whole") ? 1 : (float) Math.max(0, Math.min(1, (frame - subFrame + 1) / (0.3 * fps)));
			if (in > 0) {
				float rise = (float) (1 - TextLayout.ease(in)) * 2.5f * k;
				for (int i = 0; i < subWords.size(); i++) ink.text(subWords.get(i), subX[i], subY[i] + rise, k, 1, subColor, alpha * in, true);
			}
		}
		return true;
	}

	@Override
	void describe(JsonObject o) {
		o.addProperty("text", String.join(" ", titleWords));
		o.addProperty("subtitle", subWords.isEmpty() ? null : String.join(" ", subWords));
		o.add("lines", lines(titleWords, titleFit));
		o.add("subtitle_lines", lines(subWords, subFit));
		o.addProperty("words_count", titleWords.size() + subWords.size());
		o.addProperty("style", style);
		o.addProperty("position", position);
		o.addProperty("cap_height", titleFit == null ? null : TextLayout.CAP * titleFit.fontScale() * layout.scale());
		o.addProperty("subtitle_cap_height", subFit == null ? null : TextLayout.CAP * subFit.fontScale() * layout.scale());
		o.add("box", box(layout.toFrame(boxX0, boxY0, boxX1, boxY1)));
		if (card) {
			o.add("background_box", box(new int[] {0, 0, layout.frameWidth(), layout.frameHeight()}));
			o.addProperty("background", String.format("#%08x", background));
			o.addProperty("fade_in", fadeIn);
			o.addProperty("fade_out", fadeOut);
		}
		JsonArray ws = new JsonArray();
		for (int i = 0; i < titleWords.size(); i++) {
			JsonObject j = new JsonObject();
			j.addProperty("w", titleWords.get(i));
			j.addProperty("key", titleKeys.get(i));
			j.addProperty("frame", wordFrames[i]);
			ws.add(j);
		}
		o.add("words", ws);
		o.addProperty("reading_seconds", TextLayout.readingSeconds(titleWords.size() + subWords.size()));
	}

	private static JsonArray lines(List<String> words, TextLayout.Fit fit) {
		JsonArray a = new JsonArray();
		if (fit == null) return a;
		for (List<Integer> line : fit.lines()) {
			StringBuilder b = new StringBuilder();
			for (int i : line) b.append(b.isEmpty() ? "" : " ").append(words.get(i));
			a.add(b.toString());
		}
		return a;
	}
}
