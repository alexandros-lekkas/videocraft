package io.github.alexandroslekkas.videocraft;

import io.github.alexandroslekkas.videocraft.director.ControlServer;
import io.github.alexandroslekkas.videocraft.director.Director;
import io.github.alexandroslekkas.videocraft.director.Registries;
import io.github.alexandroslekkas.videocraft.director.Take;
import io.github.alexandroslekkas.videocraft.plan.Plan;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;

/**
 * Client entry point. Inert unless the game was started with {@code -Dvideocraft.take=<dir>} (what {@code bin/videocraft
 * run} does): then it reads {@code <dir>/plan.json}, plays it and quits. A player who installs the jar sees nothing.
 */
public final class Videocraft implements ClientModInitializer {
	public static final String MOD_ID = "videocraft";

	@Override
	public void onInitializeClient() {
		Take take = Take.fromSystemProperty();
		if (take == null) return;
		Plan plan;
		Registries registries;
		try {
			plan = Plan.read(take.plan());
			registries = Registries.load();
		} catch (Exception e) {
			VideocraftLog.LOGGER.error("VIDEOCRAFT RESULT FAIL cannot load {}: {}", take.plan(), e.getMessage());
			com.google.gson.JsonObject result = new com.google.gson.JsonObject();
			result.addProperty("verdict", "FAIL");
			result.addProperty("reason", "cannot load plan.json: " + e.getMessage());
			take.writeResult(result);
			Runtime.getRuntime().halt(1);
			return;
		}
		Director director = Director.start(take, plan, registries);
		ClientTickEvents.END_CLIENT_TICK.register(director::tick);
		ControlServer.start(Integer.getInteger("videocraft.port", 25750));
	}
}
