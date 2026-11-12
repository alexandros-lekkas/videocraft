package io.github.alexandroslekkas.videocraft.text;

import java.util.ArrayList;
import java.util.List;
import java.util.function.ToIntFunction;

/**
 * The geometry of videocraft's text, with no Minecraft classes (so plain-JVM checks can test it).
 *
 * <p>Text is laid out in <em>layout pixels</em>: pixels of a frame whose short side is 1080. A 1920x1080 frame is
 * 1920x1080 layout pixels; a 1080x1920 vertical frame is 1080x1920; a 1280x720 frame is also 1920x1080 (each layout
 * pixel two thirds of a frame pixel). So a size written in the script means the same on every frame, and the safe area
 * (DESIGN.md section 5: x 96-1824, y 54-918 at 1920x1080, that is 5% at the sides and top, 15% at the bottom) scales
 * with the frame's own width and height.
 *
 * <p>The game's font is a bitmap: capitals are 7 font pixels tall, a line 9 (with descenders), and glyphs are drawn
 * with nearest-neighbour sampling. A whole number of frame pixels per font pixel keeps the letters crisp, so a cap
 * height in the script is rounded to a multiple of 7.
 */
public final class TextLayout {
	/** Capitals are 7 font pixels tall; the font's line (with descenders) is 9, and videocraft spaces lines 11 apart. */
	public static final int CAP = 7, LINE = 11;
	/** The smallest capital height that counts as shown at phone width (DESIGN.md section 5). */
	public static final double MIN_CAP = 44;

	private final int frameWidth, frameHeight;
	private final double scale;

	/** @param frameWidth framebuffer pixels */
	public TextLayout(int frameWidth, int frameHeight) {
		this.frameWidth = frameWidth;
		this.frameHeight = frameHeight;
		this.scale = Math.min(frameWidth, frameHeight) / 1080.0;
	}

	public int frameWidth() { return frameWidth; }
	public int frameHeight() { return frameHeight; }

	/** Frame pixels per layout pixel. */
	public double scale() { return scale; }

	public double width() { return frameWidth / scale; }
	public double height() { return frameHeight / scale; }

	/** The safe area in layout pixels: {x0, y0, x1, y1}. */
	public double[] safe() {
		double w = width(), h = height();
		return new double[] {w * 0.05, h * 0.05, w * 0.95, h * 0.85};
	}

	/** The safe area in frame pixels, rounded: {x0, y0, x1, y1}. */
	public int[] safeFrame() {
		double[] s = safe();
		return new int[] {(int) Math.round(s[0] * scale), (int) Math.round(s[1] * scale), (int) Math.round(s[2] * scale), (int) Math.round(s[3] * scale)};
	}

	/** Layout pixels per font pixel for a requested cap height (layout pixels): a multiple of 7, at least 1. */
	public static int fontScale(double cap) {
		return Math.max(1, (int) Math.round(cap / CAP));
	}

	/** A box in layout pixels to frame pixels, rounded outwards. */
	public int[] toFrame(double x0, double y0, double x1, double y1) {
		return new int[] {(int) Math.floor(x0 * scale), (int) Math.floor(y0 * scale), (int) Math.ceil(x1 * scale), (int) Math.ceil(y1 * scale)};
	}

	// ---- Lines ----

	/** Text broken into lines at a font scale. {@code lines} hold word indices into the word list. */
	public record Fit(int fontScale, List<List<Integer>> lines) {
		public int lineCount() { return lines.size(); }
	}

	/**
	 * Breaks words into at most {@code maxLines} lines that fit {@code maxWidth} layout pixels, trying font scales from
	 * {@code largest} down to {@code smallest}. With {@code fewerLines} a smaller font on fewer lines wins over a larger font
	 * on more (titles); otherwise the largest font that fits in {@code maxLines} wins (captions). Two lines are balanced: the
	 * break that makes the longer line shortest, the top line the shorter on a tie. Returns null if nothing fits.
	 *
	 * @param width the width of a word in font pixels
	 * @param space the width of a space in font pixels
	 * @param forced line breaks the script asked for (a word index that starts a new line), or null
	 */
	public static Fit fit(List<String> words, ToIntFunction<String> width, int space, double maxWidth, int maxLines, int largest, int smallest,
			boolean fewerLines, List<Integer> forced) {
		if (forced != null && !forced.isEmpty()) {
			List<List<Integer>> lines = forcedLines(words.size(), forced);
			if (lines.size() > maxLines) return null;
			for (int k = largest; k >= smallest; k--) {
				boolean fits = true;
				for (List<Integer> line : lines) if (lineWidth(words, line, width, space) * k > maxWidth) fits = false;
				if (fits) return new Fit(k, lines);
			}
			return null;
		}
		if (fewerLines) {
			for (int n = 1; n <= maxLines; n++) {
				for (int k = largest; k >= smallest; k--) {
					List<List<Integer>> lines = balanced(words, width, space, maxWidth / k, n);
					if (lines != null) return new Fit(k, lines);
				}
			}
			return null;
		}
		for (int k = largest; k >= smallest; k--) {
			for (int n = 1; n <= maxLines; n++) {
				List<List<Integer>> lines = balanced(words, width, space, maxWidth / k, n);
				if (lines != null) return new Fit(k, lines);
			}
		}
		return null;
	}

	/** Width in font pixels of the words of one line, with spaces between. */
	public static int lineWidth(List<String> words, List<Integer> line, ToIntFunction<String> width, int space) {
		int w = 0;
		for (int i = 0; i < line.size(); i++) w += width.applyAsInt(words.get(line.get(i))) + (i > 0 ? space : 0);
		return w;
	}

	private static List<List<Integer>> forcedLines(int count, List<Integer> starts) {
		List<List<Integer>> lines = new ArrayList<>();
		List<Integer> line = new ArrayList<>();
		for (int i = 0; i < count; i++) {
			if (starts.contains(i) && !line.isEmpty()) { lines.add(line); line = new ArrayList<>(); }
			line.add(i);
		}
		if (!line.isEmpty()) lines.add(line);
		return lines;
	}

	/** The best break of the words into exactly {@code n} lines (n is 1, 2 or 3) within {@code max} font pixels, or null. */
	private static List<List<Integer>> balanced(List<String> words, ToIntFunction<String> width, int space, double max, int n) {
		int count = words.size();
		if (count == 0 || n > count) return null;
		List<List<Integer>> best = null;
		double bestLongest = Double.MAX_VALUE;
		int bestTop = Integer.MAX_VALUE;
		if (n == 1) {
			List<Integer> all = range(0, count);
			return lineWidth(words, all, width, space) <= max ? List.of(all) : null;
		}
		// Each break position (and pair, for three lines): small numbers of words, so try them all.
		for (int a = 1; a < count; a++) {
			for (int b = n == 3 ? a + 1 : count; b <= count; b++) {
				if (n == 3 && b >= count) break;
				List<List<Integer>> lines = n == 2 ? List.of(range(0, a), range(a, count)) : List.of(range(0, a), range(a, b), range(b, count));
				double longest = 0;
				for (List<Integer> line : lines) longest = Math.max(longest, lineWidth(words, line, width, space));
				int top = lineWidth(words, lines.getFirst(), width, space);
				if (longest > max) continue;
				if (longest < bestLongest || (longest == bestLongest && top < bestTop)) {
					best = lines;
					bestLongest = longest;
					bestTop = top;
				}
				if (n == 2) break;
			}
		}
		return best;
	}

	private static List<Integer> range(int from, int to) {
		List<Integer> out = new ArrayList<>();
		for (int i = from; i < to; i++) out.add(i);
		return out;
	}

	// ---- Time ----

	/** The shot frame on which something timed {@code seconds} into the shot appears: the nearest frame. */
	public static int frameOf(double seconds, int fps) {
		return (int) Math.round(seconds * fps);
	}

	/** How long a word takes to pop in, in seconds. */
	public static final double POP = 0.25;

	/**
	 * The scale of a word {@code frames} frames after the frame it pops on (0 on that frame): it is already visible at 60%
	 * on its first frame (so the frame it lands on is the frame it was asked for), overshoots to 112% and settles at 100%.
	 * Negative: not shown yet (0).
	 */
	public static float pop(int frames, int fps) {
		if (frames < 0) return 0;
		double k = (frames + 1) / (POP * fps);
		if (k >= 1) return 1;
		return (float) (k < 0.55 ? 0.6 + 0.52 * ease(k / 0.55) : 1.12 - 0.12 * ease((k - 0.55) / 0.45));
	}

	/** Opacity of a popping word: 70% on its first frame, opaque after a third of the pop. */
	public static float popAlpha(int frames, int fps) {
		if (frames < 0) return 0;
		double k = (frames + 1) / (POP * fps);
		return (float) Math.min(1, 0.7 + 0.3 * k / 0.33);
	}

	public static double ease(double k) {
		k = Math.max(0, Math.min(1, k));
		return 1 - (1 - k) * (1 - k);
	}

	public static double smooth(double k) {
		k = Math.max(0, Math.min(1, k));
		return k * k * (3 - 2 * k);
	}

	/** Reading time for a message to be complete on screen (DESIGN.md section 5): max(1.2 s, 0.5 s + 0.3 s a word). */
	public static double readingSeconds(int words) {
		return Math.max(1.2, 0.5 + 0.3 * words);
	}

	/** {@code #rrggbb} or {@code #aarrggbb} (or without the #) to an ARGB int; opaque when no alpha is given. */
	public static int color(String text, String where) {
		String hex = text.startsWith("#") ? text.substring(1) : text;
		try {
			if (hex.length() == 6) return 0xFF000000 | Integer.parseUnsignedInt(hex, 16);
			if (hex.length() == 8) return Integer.parseUnsignedInt(hex, 16);
		} catch (NumberFormatException e) {
			// below
		}
		throw new IllegalArgumentException(where + ": a colour is \"#rrggbb\" or \"#aarrggbb\" (got \"" + text + "\")");
	}
}
