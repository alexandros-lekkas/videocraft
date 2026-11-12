package io.github.alexandroslekkas.videocraft.text;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;

/**
 * Drawing in layout pixels (see {@link TextLayout}): outlined text in the game's font, with a drop shadow so it reads
 * on any background, and filled boxes. One instance per drawn frame; the pose is already scaled so one unit is one
 * layout pixel.
 */
final class Ink {
	static final int INK = 0xFF10141A, WHITE = 0xFFFFFFFF, YELLOW = 0xFFFFE23B;
	/** The outline ring: twelve directions at {@link #RING} font pixels, so the outline is round rather than square. */
	private static final float[][] AROUND = new float[12][];
	private static final float RING = 0.62f, SHADOW = 1.25f;

	static {
		for (int i = 0; i < AROUND.length; i++) {
			double a = i * Math.PI * 2 / AROUND.length;
			AROUND[i] = new float[] {(float) (Math.cos(a) * RING), (float) (Math.sin(a) * RING)};
		}
	}

	final GuiGraphicsExtractor graphics;
	final Font font;
	final TextLayout layout;

	Ink(GuiGraphicsExtractor graphics, TextLayout layout) {
		this.graphics = graphics;
		this.font = Minecraft.getInstance().font;
		this.layout = layout;
	}

	/** The current frame's layout: framebuffer size from the window. */
	static TextLayout layout() {
		var w = Minecraft.getInstance().getWindow();
		return new TextLayout(w.getWidth(), w.getHeight());
	}

	/** Width of a string in font pixels (the font's advance, including the pixel after the last glyph). */
	static int width(String text) { return Minecraft.getInstance().font.width(text); }

	/**
	 * Outlined text whose top-left (the top of the capitals) is at ({@code x}, {@code y}), {@code k} layout pixels a font
	 * pixel, scaled by {@code pop} about its centre.
	 */
	void text(String text, float x, float y, float k, float pop, int rgb, float alpha, boolean outline) {
		if (alpha < 0.03f || pop <= 0) return;
		var pose = graphics.pose();
		float w = font.width(text) * k, h = TextLayout.CAP * k;
		pose.pushMatrix();
		pose.translate(x + w / 2, y + h / 2);
		pose.scale(k * pop, k * pop);
		float left = -font.width(text) / 2f, top = -TextLayout.CAP / 2f;
		int a = Math.round(alpha * 255) << 24;
		if (outline) {
			int ink = a | (INK & 0xFFFFFF);
			// The shadow first, so the outline and the letters sit on it: it gives the type weight on bright skies.
			pose.pushMatrix();
			pose.translate(SHADOW * 0.35f, SHADOW);
			for (float[] o : AROUND) at(text, left + o[0], top + o[1], ink);
			pose.popMatrix();
			for (float[] o : AROUND) at(text, left + o[0], top + o[1], ink);
		}
		at(text, left, top, a | (rgb & 0xFFFFFF));
		pose.popMatrix();
	}

	private void at(String text, float x, float y, int argb) {
		var pose = graphics.pose();
		pose.pushMatrix();
		pose.translate(x, y);
		graphics.text(font, text, 0, 0, argb, false);
		pose.popMatrix();
	}

	/** A letter with depth: copies stepping down and right, darkest last, then the outline, then the face (the title look). */
	void deep(String text, float x, float y, float k, float pop, int rgb, float alpha) {
		if (alpha < 0.03f || pop <= 0) return;
		var pose = graphics.pose();
		float w = font.width(text) * k, h = TextLayout.CAP * k;
		int a = Math.round(alpha * 255) << 24;
		pose.pushMatrix();
		pose.translate(x + w / 2, y + h / 2);
		pose.scale(k * pop, k * pop);
		float left = -font.width(text) / 2f, top = -TextLayout.CAP / 2f;
		for (int depth = 4; depth >= 1; depth--) at(text, left + depth * 0.22f, top + depth * 0.34f, a | ((depth > 2 ? INK : 0xFF2B3442) & 0xFFFFFF));
		for (float[] o : AROUND) at(text, left + o[0] * 0.45f, top + o[1] * 0.45f, a | (INK & 0xFFFFFF));
		at(text, left, top, a | (rgb & 0xFFFFFF));
		pose.popMatrix();
	}

	/** A filled box in layout pixels (fractional edges allowed). */
	void box(float x0, float y0, float x1, float y1, int argb) {
		if ((argb >>> 24) == 0) return;
		var pose = graphics.pose();
		pose.pushMatrix();
		pose.translate(x0, y0);
		// fill takes whole units; draw a 1x1 unit scaled to the box so fractional sizes stay exact.
		pose.scale(x1 - x0, y1 - y0);
		graphics.fill(0, 0, 1, 1, argb);
		pose.popMatrix();
	}

	/** A vertical gradient in layout pixels. */
	void gradient(float x0, float y0, float x1, float y1, int top, int bottom) {
		var pose = graphics.pose();
		pose.pushMatrix();
		pose.translate(x0, y0);
		pose.scale((x1 - x0) / 100f, (y1 - y0) / 100f);
		graphics.fillGradient(0, 0, 100, 100, top, bottom);
		pose.popMatrix();
	}

	/** A pill (a box with its corners cut by one step) in layout pixels. */
	void pill(float x0, float y0, float x1, float y1, float step, int argb) {
		box(x0 + step, y0, x1 - step, y1, argb);
		box(x0, y0 + step, x0 + step, y1 - step, argb);
		box(x1 - step, y0 + step, x1, y1 - step, argb);
	}

	/** Multiplies the alpha of an ARGB colour. */
	static int fade(int argb, float alpha) {
		int a = Math.round(((argb >>> 24) & 0xFF) * Math.max(0, Math.min(1, alpha)));
		return (a << 24) | (argb & 0xFFFFFF);
	}

	/** Dark ink on a light colour, white on a dark one. */
	static int on(int argb) {
		int r = (argb >> 16) & 0xFF, g = (argb >> 8) & 0xFF, b = argb & 0xFF;
		return 0.2126 * r + 0.7152 * g + 0.0722 * b > 150 ? INK : WHITE;
	}
}
