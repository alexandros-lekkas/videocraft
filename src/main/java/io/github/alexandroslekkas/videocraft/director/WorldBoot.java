package io.github.alexandroslekkas.videocraft.director;

import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.plan.Plan;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.core.HolderLookup;
import net.minecraft.core.registries.Registries;
import net.minecraft.util.FileUtil;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.GameType;
import net.minecraft.world.level.LevelSettings;
import net.minecraft.world.level.WorldDataConfiguration;
import net.minecraft.world.level.levelgen.FlatLevelSource;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.levelgen.WorldDimensions;
import net.minecraft.world.level.levelgen.flat.FlatLevelGeneratorPresets;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.presets.WorldPresets;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Comparator;
import java.util.List;
import java.util.function.Function;
import java.util.concurrent.TimeUnit;

/** Getting into the take's world, and the frame size check. All the world-creation API drift stays in this file. */
final class WorldBoot {
	private WorldBoot() {}

	/** The world kinds a seed can make: {@code world.preset}. */
	static final List<String> PRESETS = List.of("default", "flat", "void");

	/**
	 * Opens a copy of {@code world.save} (a pristine world under {@code cache/worlds/}, copied fresh for every take so
	 * no take sees what the last one did; a folder already under the game's saves/ is opened as it is) or creates a fresh
	 * world from {@code world.seed} and {@code world.preset}. Returns the level id.
	 */
	static String enter(Minecraft mc, Plan.World world, String planName) {
		var source = mc.getLevelSource();
		if (world.save() != null) {
			String levelId = copySave(source.getBaseDir(), world.save());
			mc.createWorldOpenFlows().openWorld(levelId, () -> mc.gui.setScreen(new TitleScreen()));
			return levelId;
		}
		String levelId;
		try {
			levelId = FileUtil.findAvailableName(source.getBaseDir(), "videocraft-" + planName.replaceAll("[^A-Za-z0-9_-]", "-"), "");
		} catch (IOException e) {
			throw new UncheckedIOException(e);
		}
		String preset = world.params().string("preset", "default");
		if (!PRESETS.contains(preset)) throw new IllegalArgumentException("world.preset is one of " + PRESETS + ", not " + preset);
		long seed = world.seed() == null ? WorldOptions.randomSeed() : WorldOptions.parseSeed(world.seed()).orElse(WorldOptions.randomSeed());
		GameType mode = GameType.byName(world.gamemode(), GameType.CREATIVE);
		LevelSettings settings = new LevelSettings(levelId, mode, new LevelSettings.DifficultySettings(Difficulty.PEACEFUL, false, false), true, WorldDataConfiguration.DEFAULT);
		// Flat and void worlds are stages: no villages or other structures walking into them.
		boolean structures = preset.equals("default");
		mc.createWorldOpenFlows().createFreshLevel(levelId, settings, new WorldOptions(seed, structures, false), dimensions(preset), new TitleScreen());
		VideocraftLog.LOGGER.info("VIDEOCRAFT creating world {} from seed {} ({})", levelId, seed, preset);
		return levelId;
	}

	private static Function<HolderLookup.Provider, WorldDimensions> dimensions(String preset) {
		return switch (preset) {
			case "flat" -> r -> r.lookupOrThrow(Registries.WORLD_PRESET).getOrThrow(WorldPresets.FLAT).value().createWorldDimensions();
			case "void" -> r -> {
				// The superflat "The Void": no blocks at all but a small platform at the origin; sets bring their own ground.
				var flat = r.lookupOrThrow(Registries.WORLD_PRESET).getOrThrow(WorldPresets.FLAT).value().createWorldDimensions();
				var empty = r.lookupOrThrow(Registries.FLAT_LEVEL_GENERATOR_PRESET).getOrThrow(FlatLevelGeneratorPresets.THE_VOID).value().settings();
				return flat.replaceOverworldGenerator(r, new FlatLevelSource(empty));
			};
			default -> WorldPresets::createNormalWorldDimensions;
		};
	}

	/**
	 * Copies {@code cache/worlds/<name>} (the folder in {@code -Dvideocraft.worlds}) to {@code saves/videocraft-save-<name>},
	 * replacing an earlier copy. Without a cache entry, a folder of that name under saves/ is used as it is.
	 */
	static String copySave(Path saves, String name) {
		if (!name.matches("[A-Za-z0-9_.-]+") || name.startsWith(".")) throw new IllegalArgumentException("world.save is a folder name, not " + name);
		Path cache = Path.of(System.getProperty("videocraft.worlds", "cache/worlds")).toAbsolutePath().resolve(name);
		if (!Files.isDirectory(cache)) {
			if (Files.isDirectory(saves.resolve(name))) return name;
			throw new IllegalArgumentException("no world '" + name + "' in " + cache.getParent() + " (or under " + saves + ")");
		}
		if (!Files.isRegularFile(cache.resolve("level.dat"))) throw new IllegalArgumentException(cache + " has no level.dat: not a saved world");
		String levelId = "videocraft-save-" + name;
		Path target = saves.resolve(levelId);
		try {
			if (Files.exists(target)) {
				try (var walk = Files.walk(target)) {
					for (Path f : walk.sorted(Comparator.reverseOrder()).toList()) Files.delete(f);
				}
			}
			try (var walk = Files.walk(cache)) {
				for (Path f : walk.toList()) {
					Path to = target.resolve(cache.relativize(f).toString());
					// session.lock belongs to whichever game last had the world open.
					if (f.getFileName().toString().equals("session.lock")) continue;
					if (Files.isDirectory(f)) Files.createDirectories(to);
					else Files.copy(f, to, StandardCopyOption.REPLACE_EXISTING);
				}
			}
		} catch (IOException e) {
			throw new UncheckedIOException("could not copy " + cache + " to " + target, e);
		}
		VideocraftLog.LOGGER.info("VIDEOCRAFT world {} copied from {}", levelId, cache);
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
