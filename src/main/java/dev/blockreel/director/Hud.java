package dev.blockreel.director;

import dev.blockreel.BlockreelLog;
import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElementRegistry;
import net.fabricmc.fabric.api.client.rendering.v1.hud.VanillaHudElements;
import net.minecraft.resources.Identifier;

import java.util.List;

/**
 * The vanilla HUD (hotbar, hearts, crosshair and the rest) only draws while a shot is seen through the player's own eyes
 * and asks for it ({@link Director#hudVisible()}). blockreel's own text is a separate HUD layer and always draws.
 */
final class Hud {
	private static final List<String> HIDDEN = List.of("HOTBAR", "ARMOR_BAR", "HEALTH_BAR", "FOOD_BAR", "AIR_BAR", "MOUNT_HEALTH", "INFO_BAR",
		"EXPERIENCE_LEVEL", "INFO_BAR_FOREGROUND", "HELD_ITEM_TOOLTIP", "CROSSHAIR", "STATUS_EFFECTS", "SCOREBOARD", "BOSS_BAR", "SUBTITLES");
	private static boolean installed;

	private Hud() {}

	static void install() {
		if (installed) return;
		installed = true;
		for (String name : HIDDEN) {
			Identifier id;
			try {
				id = (Identifier) VanillaHudElements.class.getField(name).get(null);
			} catch (ReflectiveOperationException e) {
				BlockreelLog.LOGGER.warn("BLOCKREEL no vanilla HUD element {}", name);
				continue;
			}
			try {
				HudElementRegistry.replaceElement(id, element -> (graphics, delta) -> { if (Director.hudVisible()) element.extractRenderState(graphics, delta); });
			} catch (RuntimeException e) {
				BlockreelLog.LOGGER.warn("BLOCKREEL the HUD element {} stays on in every shot: {}", id, e.toString());
			}
		}
	}
}
