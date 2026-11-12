package dev.blockreel;

import dev.blockreel.director.ControlServer;
import dev.blockreel.director.Director;
import dev.blockreel.director.Registries;
import dev.blockreel.director.Take;
import dev.blockreel.plan.Plan;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;

/**
 * Client entry point. Inert unless the game was started with {@code -Dblockreel.take=<dir>} (what {@code bin/blockreel
 * run} does): then it reads {@code <dir>/plan.json}, plays it and quits. A player who installs the jar sees nothing.
 */
public final class Blockreel implements ClientModInitializer {
	public static final String MOD_ID = "blockreel";

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
			BlockreelLog.LOGGER.error("BLOCKREEL RESULT FAIL cannot load {}: {}", take.plan(), e.getMessage());
			com.google.gson.JsonObject result = new com.google.gson.JsonObject();
			result.addProperty("verdict", "FAIL");
			result.addProperty("reason", "cannot load plan.json: " + e.getMessage());
			take.writeResult(result);
			Runtime.getRuntime().halt(1);
			return;
		}
		Director director = Director.start(take, plan, registries);
		ClientTickEvents.END_CLIENT_TICK.register(director::tick);
		ControlServer.start(Integer.getInteger("blockreel.port", 25750));
	}
}
