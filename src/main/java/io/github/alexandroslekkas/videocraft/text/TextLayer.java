package io.github.alexandroslekkas.videocraft.text;

import io.github.alexandroslekkas.videocraft.Videocraft;
import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElementRegistry;
import net.fabricmc.fabric.api.client.screen.v1.ScreenEvents;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.resources.Identifier;

import java.util.EnumMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;

/**
 * Where videocraft's own text is drawn: a HUD layer over the world, and the same layer over any open screen (a
 * caption drawn as a Screen could not overlap another screen). The ffmpeg most people have (Homebrew's) has no
 * drawtext, so all text is drawn here, in the game's font, and captured with the frame.
 *
 * <p>Two kinds of things are on it: {@link Item}s anyone can add (the actors workstream's drawn pointer), drawn in GUI
 * pixels; and the text actions' messages, drawn in layout pixels ({@link TextLayout}). One message at a time: showing a
 * caption, title, card or lower third replaces the one on screen, on that very frame. A keycap has its own slot.
 */
public final class TextLayer {
	/** Something drawn on the layer. Coordinates are GUI pixels; at 1920x1080 with GUI scale 4 that is 480x270. */
	public interface Item {
		void draw(GuiGraphicsExtractor graphics);
	}

	private static final List<Item> ITEMS = new CopyOnWriteArrayList<>();
	private static final Map<Message.Slot, Message> SHOWN = new EnumMap<>(Message.Slot.class);
	private static boolean installed;

	private TextLayer() {}

	public static void add(Item item) { ITEMS.add(item); }

	public static void remove(Item item) { ITEMS.remove(item); }

	/** Removes every item and message (messages are ended as cleared). */
	public static void clear() {
		ITEMS.clear();
		clearMessages(null);
	}

	/** Ends the message in a slot (or in every slot when null), as a {@code clear} cue does. */
	static void clearMessages(Message.Slot slot) {
		for (Message.Slot s : Message.Slot.values()) {
			Message m = SHOWN.get(s);
			if (m != null && (slot == null || slot == s)) m.end("clear");
		}
	}

	/** Puts a message on screen, ending the one in its slot (the new one replaces it on this frame). */
	static void show(Message message) {
		Message old = SHOWN.put(message.slot(), message);
		if (old != null && old != message) old.end("replaced");
	}

	static void remove(Message message) {
		SHOWN.remove(message.slot(), message);
	}

	public static void install() {
		if (installed) return;
		installed = true;
		HudElementRegistry.addLast(Identifier.fromNamespaceAndPath(Videocraft.MOD_ID, "text"),
			(graphics, delta) -> { if (Minecraft.getInstance().gui.screen() == null) draw(graphics); });
		ScreenEvents.AFTER_INIT.register((client, screen, w, h) ->
			ScreenEvents.afterExtract(screen).register((s, graphics, mouseX, mouseY, delta) -> draw(graphics)));
	}

	private static void draw(GuiGraphicsExtractor graphics) {
		if (!SHOWN.isEmpty()) {
			TextLayout layout = Ink.layout();
			// One unit is one layout pixel: GUI pixels per layout pixel = (frame pixels per layout pixel) / GUI scale.
			float unit = (float) (layout.scale() * graphics.guiWidth() / layout.frameWidth());
			var pose = graphics.pose();
			pose.pushMatrix();
			pose.scale(unit, unit);
			Ink ink = new Ink(graphics, layout);
			// The message first, a keycap over it; each on its own stratum so one's boxes never cover the other's text.
			for (Message.Slot slot : Message.Slot.values()) {
				Message m = SHOWN.get(slot);
				if (m == null) continue;
				graphics.nextStratum();
				m.draw(ink);
			}
			pose.popMatrix();
		}
		for (Item item : ITEMS) item.draw(graphics);
	}
}
