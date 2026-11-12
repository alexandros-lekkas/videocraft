package io.github.alexandroslekkas.videocraft.actor;

import java.util.Locale;
import java.util.Map;

/**
 * What kind of body an actor has, as far as acting goes: its paces for each gait (blocks per second), how far its head
 * turns on its neck, how lively its idle life is, and how its head is carried on a strut. Paces stay under the speed
 * at which vanilla's walk cycle stops matching the ground (about 5 blocks a second), so feet never slide.
 */
record Breed(double walk, double strut, double trot, double run, double reach, Life.Temper temper, double chin, double headSpeed) {
	static final Breed HUMAN = new Breed(2.3, 2.0, 3.6, 4.8, 60, Life.Temper.CALM, -2, 15);
	static final Breed ANIMAL = new Breed(1.6, 1.8, 3.0, 4.4, 50, Life.Temper.CALM, -8, 15);
	static final Breed BIRD = new Breed(1.0, 1.1, 1.8, 2.6, 55, Life.Temper.BUSY, -6, 28);

	private static final Map<String, Breed> BY_ID = Map.ofEntries(
		Map.entry("minecraft:mannequin", HUMAN),
		Map.entry("minecraft:villager", HUMAN),
		Map.entry("minecraft:wandering_trader", HUMAN),
		Map.entry("minecraft:iron_golem", new Breed(1.3, 1.2, 2.2, 3.0, 40, Life.Temper.CALM, -2, 10)),
		Map.entry("minecraft:goat", new Breed(1.6, 1.8, 3.0, 4.4, 40, Life.Temper.CALM, -14, 14)),
		Map.entry("minecraft:fox", new Breed(1.7, 1.9, 3.2, 4.6, 55, Life.Temper.CALM, -6, 17)),
		Map.entry("minecraft:chicken", BIRD),
		Map.entry("minecraft:parrot", BIRD),
		Map.entry("minecraft:bee", new Breed(1.4, 1.4, 2.4, 3.6, 30, Life.Temper.BUSY, 0, 22)),
		Map.entry("minecraft:cat", new Breed(1.5, 1.7, 3.2, 4.6, 55, Life.Temper.CALM, -6, 16)),
		Map.entry("minecraft:wolf", new Breed(1.8, 2.0, 3.4, 4.8, 50, Life.Temper.CALM, -6, 15)),
		Map.entry("minecraft:sheep", ANIMAL),
		Map.entry("minecraft:cow", new Breed(1.3, 1.4, 2.4, 3.6, 40, Life.Temper.CALM, -4, 10)),
		Map.entry("minecraft:pig", new Breed(1.3, 1.4, 2.4, 3.6, 40, Life.Temper.CALM, -4, 12)));

	static Breed of(String entity) { return BY_ID.getOrDefault(entity, ANIMAL); }

	/** Blocks per second for a named gait. */
	double pace(String gait, String where) {
		return switch (gait.toLowerCase(Locale.ROOT)) {
			case "walk" -> walk;
			case "strut" -> strut;
			case "trot" -> trot;
			case "run" -> run;
			default -> throw new IllegalArgumentException(where + ": gait is walk, strut, trot or run, not '" + gait + "'");
		};
	}
}
