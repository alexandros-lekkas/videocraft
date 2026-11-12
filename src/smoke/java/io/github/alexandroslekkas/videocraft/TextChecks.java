package io.github.alexandroslekkas.videocraft;

import io.github.alexandroslekkas.videocraft.text.TextLayout;

import java.util.Arrays;
import java.util.List;

/** Text layout without Minecraft: layout pixels on landscape and vertical frames, the safe area, line fitting, the pop. */
public final class TextChecks {
	public static void main(String[] args) {
		// A 1920x1080 frame is 1920x1080 layout pixels; its safe area is DESIGN.md's x 96-1824, y 54-918.
		TextLayout land = new TextLayout(1920, 1080);
		PlanChecks.check(land.scale() == 1 && Arrays.equals(land.safeFrame(), new int[] {96, 54, 1824, 918}), "landscape safe area " + Arrays.toString(land.safeFrame()));
		// A vertical 1080x1920 frame keeps one frame pixel a layout pixel; the safe area follows its own width and height.
		TextLayout tall = new TextLayout(1080, 1920);
		PlanChecks.check(tall.scale() == 1 && Arrays.equals(tall.safeFrame(), new int[] {54, 96, 1026, 1632}), "vertical safe area " + Arrays.toString(tall.safeFrame()));
		// 1280x720: the same layout as 1080p, two thirds of a frame pixel each.
		TextLayout small = new TextLayout(1280, 720);
		PlanChecks.check(Math.abs(small.width() - 1920) < 1e-9 && Math.abs(small.height() - 1080) < 1e-9, "720p layout is 1920x1080");
		// Cap heights round to whole font pixels: 63 px is 9 a font pixel; 44 px is the floor (6.3 → 6 would be 42, so 7).
		PlanChecks.check(TextLayout.fontScale(63) == 9 && TextLayout.fontScale(56) == 8, "font scale");
		// Fitting: six-pixel letters (5 + 1 spacing), four-pixel spaces.
		List<String> words = List.of("Best", "jumper", "in", "the", "whole", "valley.");
		TextLayout.Fit one = TextLayout.fit(words, w -> w.length() * 6, 4, 1728, 2, 9, 7, false, null);
		PlanChecks.check(one != null && one.lineCount() == 1 && one.fontScale() == 9, "fits one line at 1080p: " + one);
		TextLayout.Fit two = TextLayout.fit(words, w -> w.length() * 6, 4, 972, 2, 9, 7, false, null);
		PlanChecks.check(two != null && two.lineCount() == 2 && two.fontScale() == 9, "two lines on a vertical frame: " + two);
		// Balanced: the longer line as short as it can be.
		PlanChecks.check(two.lines().get(0).equals(List.of(0, 1, 2)) || two.lines().get(0).equals(List.of(0, 1, 2, 3)), "balanced break: " + two.lines());
		// Forced breaks are kept; too much text for two lines does not fit at all.
		TextLayout.Fit forced = TextLayout.fit(words, w -> w.length() * 6, 4, 1728, 2, 9, 7, false, List.of(2));
		PlanChecks.check(forced != null && forced.lines().get(1).getFirst() == 2, "forced break");
		List<String> lots = List.of("a", "very", "long", "caption", "that", "keeps", "going", "and", "going", "and", "going", "on", "and", "on", "forever", "more");
		PlanChecks.check(TextLayout.fit(lots, w -> w.length() * 6, 4, 972, 2, 9, 7, false, null) == null, "too long for two lines");
		// Titles prefer one line at a smaller size.
		TextLayout.Fit title = TextLayout.fit(List.of("NIBS", "vs", "DUKE"), w -> w.length() * 6, 4, 972, 2, 16, 7, true, null);
		PlanChecks.check(title != null && title.lineCount() == 1 && title.fontScale() < 16, "title on one line: " + title);
		// The pop: visible on its own frame, overshoot, then settled; nothing before.
		PlanChecks.check(TextLayout.pop(-1, 60) == 0 && TextLayout.pop(0, 60) >= 0.6f && TextLayout.pop(15, 60) == 1, "pop");
		float peak = 0;
		for (int f = 0; f < 15; f++) peak = Math.max(peak, TextLayout.pop(f, 60));
		PlanChecks.check(peak > 1.05f && peak < 1.15f, "pop overshoots: " + peak);
		PlanChecks.check(TextLayout.frameOf(0.25, 60) == 15 && TextLayout.frameOf(1 / 120.0 + 1e-9, 60) == 1, "frame of a time is the nearest frame");
		PlanChecks.check(TextLayout.readingSeconds(2) == 1.2 && Math.abs(TextLayout.readingSeconds(5) - 2.0) < 1e-9, "reading time");
		PlanChecks.check(TextLayout.color("#ff0000", "x") == 0xFFFF0000 && TextLayout.color("80000000", "x") == 0x80000000, "colours");
		System.out.println("TextChecks PASS");
	}
}
