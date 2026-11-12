package io.github.alexandroslekkas.videocraft.director;

import io.github.alexandroslekkas.videocraft.mixin.AnimationStateAccessor;
import io.github.alexandroslekkas.videocraft.mixin.AtlasAccessor;
import io.github.alexandroslekkas.videocraft.mixin.FogAccessor;
import io.github.alexandroslekkas.videocraft.mixin.RainFogAccessor;
import io.github.alexandroslekkas.videocraft.mixin.TextureManagerAccessor;
import io.github.alexandroslekkas.videocraft.mixin.TimerAccessor;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.texture.TextureAtlas;
import net.minecraft.util.RandomSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.LightLayer;

import java.util.Random;

/**
 * What makes two takes of one plan draw the same pixels. Before a shot's pre-roll, everything on the client that
 * carries state from however long the take took to get there is put back to a known start: the clock's phase within
 * a tick, the client's game time (clouds), the client's randoms (particles, falling leaves), every entity's tick count
 * and random, the animated textures' frames, and the particles in the air. Server-side state is not touched.
 */
public final class Film {
	private Film() {}

	/** Ticks of shots so far, the game time the client sees while a shot runs; -1 between shots and with no take. */
	private static long ticks = -1, total;
	private static boolean running;
	private static Random sequence = new Random(0);

	/** The client's game time while a shot runs, or -1 to leave the game's. */
	public static long gameTime() {
		return running && Director.current() != null ? ticks : -1;
	}

	/** A random for a client-side draw (a particle, a leaf, a new entity): from the take's seed on the render thread. */
	public static RandomSource random() {
		Minecraft mc = Minecraft.getInstance();
		if (!running || Director.current() == null || mc == null || !mc.isSameThread()) return RandomSource.create();
		return RandomSource.create(sequence.nextLong());
	}

	/** One client tick of a running shot (called at the end of each client tick). */
	static void tick() {
		if (running) ticks++;
	}

	/** The shot ends: game time stops counting until the next one starts. */
	static void cut() {
		if (running) total = ticks;
		running = false;
	}

	/** The rain fog the game eases toward where the camera is (AtmosphericFogEnvironment.updateRainFogState). */
	private static float rainFog(Minecraft mc, float rain) {
		var pos = mc.gameRenderer.mainCamera().blockPosition();
		boolean precipitation = mc.level.getBiome(pos).value().hasPrecipitation();
		float sky = Math.clamp((mc.level.getLightEngine().getLayerListener(LightLayer.SKY).getLightValue(pos) - 8f) / 7f, 0f, 1f);
		return rain * sky * (precipitation ? 1f : 0.5f);
	}

	/** One line of what the sky and fog are computed from, for checking that two takes start alike. */
	static String state(Minecraft mc) {
		if (mc.level == null) return "no level";
		var cam = mc.gameRenderer.mainCamera();
		var probe = cam.attributeProbe();
		return String.format(java.util.Locale.ROOT, "day %d game %d rain %.4f thunder %.4f cam %s fog %.2f-%.2f sky %s skyfog %.2f light %.3f",
			mc.level.getOverworldClockTime(), mc.level.getLevelData().getGameTime(), mc.level.getRainLevel(1), mc.level.getThunderLevel(1), cam.position(),
			probe.getValue(net.minecraft.world.attribute.EnvironmentAttributes.FOG_START_DISTANCE, 1), probe.getValue(net.minecraft.world.attribute.EnvironmentAttributes.FOG_END_DISTANCE, 1),
			probe.getValue(net.minecraft.world.attribute.EnvironmentAttributes.SKY_COLOR, 1), probe.getValue(net.minecraft.world.attribute.EnvironmentAttributes.SKY_FOG_END_DISTANCE, 1),
			probe.getValue(net.minecraft.world.attribute.EnvironmentAttributes.SKY_LIGHT_FACTOR, 1));
	}

	/** Puts the client into the same state for this shot in every take (see the class comment). */
	static void rebase(Minecraft mc, long seed, String shot, String weather) {
		long base = seed * 31 + shot.hashCode();
		// The fraction of a tick carried over from real time before the clock was fixed.
		if (mc.getDeltaTracker() instanceof TimerAccessor timer) timer.videocraft$residual(0f);
		ticks = total;
		running = true;
		sequence = new Random(base);
		if (mc.level != null) {
			mc.level.getRandom().setSeed(base ^ 0x5DEECE66DL);
			for (Entity e : mc.level.entitiesForRendering()) {
				e.tickCount = 1000 + Math.floorMod(e.getId() * 7919, 400);
				e.getRandom().setSeed(base ^ (e.getId() * 0x9E3779B97F4A7C15L));
			}
		}
		mc.particleEngine.clearParticles();
		// The weather exactly as asked, not part-way through easing out of whatever the new world started with.
		if (mc.level != null) {
			float rain = weather.equals("clear") ? 0 : 1, thunder = weather.equals("thunder") ? 1 : 0;
			mc.level.setRainLevel(rain);
			mc.level.setThunderLevel(thunder);
			for (var fog : FogAccessor.videocraft$environments()) {
				if (fog instanceof RainFogAccessor r) r.videocraft$rainFog(rain == 0 ? 0 : rainFog(mc, rain));
			}
		}
		for (var texture : ((TextureManagerAccessor) mc.getTextureManager()).videocraft$tickable()) {
			if (!(texture instanceof TextureAtlas atlas)) continue;
			for (var state : ((AtlasAccessor) atlas).videocraft$animations()) {
				var s = (AnimationStateAccessor) state;
				s.videocraft$frame(0);
				s.videocraft$subFrame(0);
				s.videocraft$dirty(true);
			}
		}
	}
}
