package io.github.alexandroslekkas.videocraft.actor;

import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.plan.Plan;
import net.minecraft.client.Minecraft;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Stages the actors of a take on arrival in the world. Owned by workstream (b). Today: the player only. Planned
 * (docs/DESIGN.md, "Actors"): NPCs as vanilla Mannequins (player-shaped, skinnable, posable) moved by videocraft.
 */
public final class Cast {
	private Cast() {}

	public static Map<String, Actor> stage(List<Plan.ActorSpec> specs, Minecraft mc) {
		Map<String, Actor> cast = new LinkedHashMap<>();
		cast.put("player", new PlayerActor(mc));
		for (Plan.ActorSpec spec : specs) {
			if (spec.id().equals("player")) continue;
			throw new IllegalArgumentException("actors." + spec.id() + ": " + spec.kind() + " actors are not implemented yet (workstream b)");
		}
		return cast;
	}
}
