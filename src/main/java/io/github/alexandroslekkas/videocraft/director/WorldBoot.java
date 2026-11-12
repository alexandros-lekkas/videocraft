package io.github.alexandroslekkas.videocraft.director;

import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.plan.Plan;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.util.FileUtil;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.LevelSettings;
import net.minecraft.world.level.WorldDataConfiguration;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.presets.WorldPresets;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.util.concurrent.TimeUnit;

/** Getting into the take's world, and the frame size check. All the world-creation API drift stays in this file. */
final class WorldBoot {
	private WorldBoot() {}

	/**
	 * Opens {@code world.save} (a folder under the game's saves/, which the CLI copied there for this take) or creates a
	 * fresh world from {@code world.seed}. Returns the level id.
	 */
	static String enter(Minecraft mc, Plan.World world, String planName) {
		var source = mc.getLevelSource();
		if (world.save() != null) {
			if (!Files.isDirectory(source.getBaseDir().resolve(world.save()))) throw new IllegalArgumentException("no save '" + world.save() + "' under " + source.getBaseDir());
			mc.createWorldOpenFlows().openWorld(world.save(), () -> mc.gui.setScreen(new TitleScreen()));
			return world.save();
		}
		String levelId;
		try {
			levelId = FileUtil.findAvailableName(source.getBaseDir(), "videocraft-" + planName.replaceAll("[^A-Za-z0-9_-]", "-"), "");
		} catch (IOException e) {
			throw new UncheckedIOException(e);
		}
		long seed = world.seed() == null ? WorldOptions.randomSeed() : WorldOptions.parseSeed(world.seed()).orElse(WorldOptions.randomSeed());
		GameType mode = GameType.byName(world.gamemode(), GameType.CREATIVE);
		LevelSettings settings = new LevelSettings(levelId, mode, new LevelSettings.DifficultySettings(Difficulty.PEACEFUL, false, false), true, WorldDataConfiguration.DEFAULT);
		mc.createWorldOpenFlows().createFreshLevel(levelId, settings, new WorldOptions(seed, true, false), WorldPresets::createNormalWorldDimensions, new TitleScreen());
		VideocraftLog.LOGGER.info("VIDEOCRAFT creating world {} from seed {}", levelId, seed);
		return levelId;
	}

	/**
	 * The middle of the world spawn block, standing on the highest block that stops movement there. Asked of the
	 * integrated server (the client may not have the heightmap yet); the same world always gives the same point.
	 */
	static Vec3 spawnPoint(Minecraft mc) {
		var server = mc.getSingleplayerServer();
		if (server == null) throw new IllegalStateException("no integrated server to ask for the spawn point");
		try {
			return server.submit(() -> {
				var level = server.overworld();
				var pos = level.getRespawnData().pos();
				int y = level.getHeight(Heightmap.Types.MOTION_BLOCKING, pos.getX(), pos.getZ());
				if (y <= level.getMinY()) y = pos.getY();
				return new Vec3(pos.getX() + 0.5, y, pos.getZ() + 0.5);
			}).get(10, TimeUnit.SECONDS);
		} catch (Exception e) {
			throw new IllegalStateException("could not read the world spawn point: " + e, e);
		}
	}

	/**
	 * Whether the framebuffer is the planned size; if not, asks the window for it once (the window is in points, the
	 * framebuffer in pixels: a 960x540 window is 1920x1080 on a 2x display).
	 */
	static boolean frameSize(Minecraft mc, int width, int height) {
		var window = mc.getWindow();
		if (window.getWidth() == width && window.getHeight() == height) return true;
		if (!asked) {
			asked = true;
			double scale = window.getScreenWidth() == 0 ? 1 : window.getWidth() / (double) window.getScreenWidth();
			int w = (int) Math.round(width / scale), h = (int) Math.round(height / scale);
			VideocraftLog.LOGGER.info("VIDEOCRAFT framebuffer {}x{} (window {}x{}); resizing the window to {}x{} for {}x{}", window.getWidth(), window.getHeight(),
				window.getScreenWidth(), window.getScreenHeight(), w, h, width, height);
			window.setWindowed(w, h);
		}
		return false;
	}

	private static boolean asked;

	static String sizeProblem(Minecraft mc, int width, int height) {
		var window = mc.getWindow();
		return "the framebuffer is " + window.getWidth() + "x" + window.getHeight() + ", not " + width + "x" + height
			+ " (window " + window.getScreenWidth() + "x" + window.getScreenHeight() + "); pass a window size that gives it (--window WxH)";
	}
}
