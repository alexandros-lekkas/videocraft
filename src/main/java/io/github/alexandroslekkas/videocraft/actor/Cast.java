package io.github.alexandroslekkas.videocraft.actor;

import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.director.Take;
import io.github.alexandroslekkas.videocraft.plan.Plan;
import net.minecraft.client.Minecraft;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Stages the actors of a take on arrival in the world: the player, and a {@link Puppet} for each {@code [[actor]]}
 * ({@code kind = "mob"} with an {@code entity} id, or {@code kind = "mannequin"}, a player-shaped NPC). A puppet's
 * entity appears on the first frame after arrival, at its {@code at} (so anchors defined by staging work), and keeps
 * its place, pose and items from shot to shot until the script moves it.
 */
public final class Cast {
	private Cast() {}

	public static Map<String, Actor> stage(List<Plan.ActorSpec> specs, Minecraft mc) {
		Puppets.clear();
		Map<String, Actor> cast = new LinkedHashMap<>();
		long seed = seed();
		PlayerActor player = new PlayerActor(mc);
		player.seed(seed);
		cast.put("player", player);
		for (Plan.ActorSpec spec : specs) {
			if (spec.id().equals("player")) continue;
			var p = spec.params();
			String where = p.where();
			String kind = spec.kind().equals("npc") ? "mannequin" : spec.kind();
			String entity = switch (kind) {
				case "mob" -> {
					if (!p.has("entity")) throw new IllegalArgumentException(where + ": a mob actor needs entity = \"minecraft:<id>\" (goat, fox, chicken, ...)");
					String e = p.string("entity");
					yield e.contains(":") ? e : "minecraft:" + e;
				}
				case "mannequin" -> "minecraft:mannequin";
				default -> throw new IllegalArgumentException(where + ": kind is \"mob\" or \"mannequin\", not '" + spec.kind() + "'");
			};
			if (!p.has("at")) throw new IllegalArgumentException(where + ": an actor needs at = [x, y, z] or { anchor = ..., offset = [...] }");
			if (cast.containsKey(spec.id())) throw new IllegalArgumentException(where + ": the actor id '" + spec.id() + "' is used twice");
			cast.put(spec.id(), new Puppet(new Puppet.Spec(spec.id(), kind, entity, p, seed)));
		}
		return cast;
	}

	/** The take's seed, so idle life and timing vary with it (same plan and seed, same take). */
	private static long seed() {
		Take take = Take.fromSystemProperty();
		if (take == null) return 1;
		try {
			return Plan.read(take.plan()).seed();
		} catch (IOException | RuntimeException e) {
			return 1;
		}
	}
}
