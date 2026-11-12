package io.github.alexandroslekkas.videocraft.actor;

import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;

import java.util.Random;
import java.util.Set;

/**
 * What the game knows about flyers, for {@link Flight}: which entities start in the air, their cruise speeds, the
 * sound their wings make (a bee's buzz is its own loop sample, replayed on the frame clock so the sound log has it),
 * and an actor as an {@link Flight.Anchor} to circle or to sit on.
 */
final class Flights {
	private Flights() {}

	private static final Set<String> AIRBORNE = Set.of("minecraft:bee", "minecraft:allay", "minecraft:bat", "minecraft:vex",
		"minecraft:phantom", "minecraft:ghast", "minecraft:happy_ghast", "minecraft:blaze");

	/** Whether an entity starts in the air unless the script says {@code flying = false}. */
	static boolean airborne(String entity) { return AIRBORNE.contains(entity); }

	/** A cruise speed in blocks a second for {@code fly} and {@code land}. */
	static double speed(String entity) {
		return switch (entity) {
			case "minecraft:bee" -> 2.6;
			case "minecraft:parrot" -> 3.6;
			case "minecraft:allay" -> 3.0;
			case "minecraft:bat" -> 4.2;
			case "minecraft:chicken" -> 2.0;
			case "minecraft:phantom" -> 6.0;
			case "minecraft:vex" -> 4.0;
			default -> 3.0;
		};
	}

	/** A flyer's wing sound: which, how loud, at what pitch, and every how many seconds it is replayed. */
	record Buzz(SoundEvent sound, double volume, double pitch, double every) {}

	/**
	 * The sound a flyer makes while airborne. The bee's loop samples are 4.2 to 5.9 s long; replayed every two seconds
	 * or so they overlap into a steady buzz that moves with the bee (each copy starts where the bee is).
	 */
	static Buzz buzz(String entity, boolean angry) {
		return switch (entity) {
			case "minecraft:bee" -> angry ? new Buzz(SoundEvents.BEE_LOOP_AGGRESSIVE, 0.45, 1, 2.1) : new Buzz(SoundEvents.BEE_LOOP, 0.4, 1, 2.1);
			case "minecraft:bat" -> new Buzz(SoundEvents.BAT_LOOP, 0.25, 1, 2.4);
			case "minecraft:parrot" -> new Buzz(SoundEvents.PARROT_FLY, 0.35, 1, 0.55);
			case "minecraft:phantom" -> new Buzz(SoundEvents.PHANTOM_FLAP, 0.5, 1, 0.9);
			default -> null;
		};
	}

	/** When the first buzz of a flyer that starts in the air plays: soon, seeded, so a swarm does not start in unison. */
	static double firstBuzz(Random random) { return 0.05 + random.nextDouble() * 0.6; }

	/** An actor seen by a flyer: its feet, heading and body size, as of the tick being computed. */
	static final class ActorAnchor implements Flight.Anchor {
		private final Actor actor;

		ActorAnchor(Actor actor) { this.actor = actor; }

		Actor actor() { return actor; }

		/** A puppet anchor is ticked up to {@code tick} first, so whoever rides on it does not trail it by a tick. */
		void catchUp(ShotContext shot, long tick) {
			if (actor instanceof Puppet p) p.catchUp(shot, tick);
		}

		@Override
		public double[] feet() {
			if (actor instanceof Puppet p) {
				Vec3 f = p.feet();
				return new double[] {f.x, f.y, f.z};
			}
			Entity e = actor.entity();
			if (e != null) return new double[] {e.getX(), e.getY(), e.getZ()};
			Vec3 g = actor.ground();
			return new double[] {g.x, g.y, g.z};
		}

		@Override
		public double yaw() { return actor instanceof Puppet p ? p.bodyYaw() : actor.heading(); }

		@Override
		public double width() { Entity e = actor.entity(); return e == null ? 0.6 : e.getBbWidth(); }

		@Override
		public double height() { Entity e = actor.entity(); return e == null ? 1.8 : e.getBbHeight(); }
	}
}
