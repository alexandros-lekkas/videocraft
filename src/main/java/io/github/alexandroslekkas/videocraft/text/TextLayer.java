package io.github.alexandroslekkas.videocraft.text;

import io.github.alexandroslekkas.videocraft.Videocraft;
import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElementRegistry;
import net.fabricmc.fabric.api.client.screen.v1.ScreenEvents;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.resources.Identifier;

import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Where videocraft's own text is drawn: a HUD layer over the world, and the same layer over any open screen (a
 * caption drawn as a Screen could not overlap another screen). Owned by workstream (c). The ffmpeg most people have
 * (Homebrew's) has no drawtext, so all text is drawn here, in the game's font, and captured with the frame.
 */
public final class TextLayer {
	/** Something drawn on the layer. Coordinates are GUI pixels; at 1920x1080 with GUI scale 4 that is 480x270. */
	public interface Item {
		void draw(GuiGraphicsExtractor graphics);
	}

	private static final List<Item> ITEMS = new CopyOnWriteArrayList<>();
	private static boolean installed;

	private TextLayer() {}

	public static void add(Item item) { ITEMS.add(item); }

	public static void remove(Item item) { ITEMS.remove(item); }

	public static void clear() { ITEMS.clear(); }

	public static void install() {
		if (installed) return;
		installed = true;
		HudElementRegistry.addLast(Identifier.fromNamespaceAndPath(Videocraft.MOD_ID, "text"),
			(graphics, delta) -> { if (Minecraft.getInstance().gui.screen() == null) draw(graphics); });
		ScreenEvents.AFTER_INIT.register((client, screen, w, h) ->
			ScreenEvents.afterExtract(screen).register((s, graphics, mouseX, mouseY, delta) -> draw(graphics)));
	}

	private static void draw(GuiGraphicsExtractor graphics) {
		for (Item item : ITEMS) item.draw(graphics);
	}
}
