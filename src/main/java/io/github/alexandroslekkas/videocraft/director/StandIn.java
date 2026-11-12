package io.github.alexandroslekkas.videocraft.director;

import io.github.alexandroslekkas.videocraft.api.Action;
import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import net.minecraft.client.Minecraft;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.List;

/**
 * A stand-in: a client-side entity that the runtime moves exactly along a path, so camera rigs can be checked against
 * a known subject whatever the actors workstream is doing. Not an actor for the film (no gait, no life); real
 * characters are {@code [[actor]]}s. Staged with {@code do = "stand_in"} in {@code [[world.stage]]}, moved with
 * {@code do = "glide"}. Its position is a pure function of the shot clock, so it is reproducible.
 */
final class StandIn implements Actor {
	private static int nextId = -7_900_100;

	private final String id;
	private final Entity entity;
	private Vec3 ground, velocity = Vec3.ZERO;
	private float heading;

	private StandIn(String id, Entity entity, Vec3 at, float heading) {
		this.id = id;
		this.entity = entity;
		this.ground = at;
		this.heading = heading;
		place();
	}

	/** {@code {do = "stand_in", id = "dummy", place = [x, y, z], facing = 0, entity = "minecraft:mannequin"}}. */
	static StandIn stage(Params p, ShotContext shot) {
		String id = p.string("id");
		String type = p.string("entity", "minecraft:mannequin");
		var entityType = BuiltInRegistries.ENTITY_TYPE.getOptional(Identifier.parse(type))
			.orElseThrow(() -> new IllegalArgumentException(p.where() + ": no entity type '" + type + "'"));
		Minecraft mc = shot.minecraft();
		Entity e = entityType.create(mc.level, EntitySpawnReason.COMMAND);
		if (e == null) throw new IllegalArgumentException(p.where() + ": '" + type + "' cannot be made on the client");
		e.setId(nextId--);
		e.setNoGravity(true);
		e.setSilent(true);
		e.noPhysics = true;
		StandIn s = new StandIn(id, e, shot.position(p, "place"), (float) p.number("facing", 0));
		mc.level.addEntity(e);
		return s;
	}

	@Override public String id() { return id; }
	@Override public Entity entity() { return entity; }
	@Override public Vec3 ground() { return ground; }
	@Override public float heading() { return heading; }
	@Override public Vec3 head() { return ground.add(0, entity.getEyeHeight(), 0); }
	@Override public Vec3 velocity() { return velocity; }

	/** Puts the entity where the stand-in is, with no interpolation left over from the last tick. */
	private void place() {
		entity.snapTo(ground.x, ground.y, ground.z, heading, 0);
		entity.setOldPosAndRot();
		entity.setDeltaMovement(Vec3.ZERO);
		if (entity instanceof LivingEntity l) {
			l.yBodyRot = l.yBodyRotO = heading;
			l.yHeadRot = l.yHeadRotO = heading;
		}
	}

	void move(Vec3 to, float yaw, Vec3 speed) {
		ground = to;
		heading = yaw;
		velocity = speed;
		place();
	}

	@Override
	public void frame(ShotContext shot) { place(); }

	/**
	 * {@code {do = "glide", actor = "dummy", path = [p0, p1, ...], speed = 1.4, ease = 0.5, mark = "arrived"}}: along a
	 * Catmull-Rom curve through the points at {@code speed} blocks per second, speeding up and slowing down over
	 * {@code ease} seconds, facing the way it goes (a chord of 1.2 blocks, so corners turn smoothly). Notes {@code mark}
	 * on arrival.
	 */
	static Action glide(Params p, ShotContext shot, StandIn who) {
		List<Vec3> points = new ArrayList<>();
		var array = p.raw("path");
		if (array == null || !array.isJsonArray() || array.getAsJsonArray().size() < 2) throw new IllegalArgumentException(p.where() + ": path is a list of at least two positions");
		for (int i = 0; i < array.getAsJsonArray().size(); i++) {
			var o = new com.google.gson.JsonObject();
			o.add("p", array.getAsJsonArray().get(i));
			points.add(shot.position(new Params(o, p.where() + ".path[" + i + "]"), "p"));
		}
		double speed = p.number("speed", 1.4), ease = p.number("ease", 0.5);
		if (speed <= 0) throw new IllegalArgumentException(p.where() + ": speed must be > 0");
		String mark = p.string("mark", null);
		Path path = Path.through(points);
		double start = shot.seconds();
		return new Action() {
			@Override
			public boolean frame(ShotContext s) {
				double t = s.seconds() - start;
				double along = path.travelled(t, speed, ease);
				Vec3 at = path.at(along);
				Vec3 ahead = path.at(Math.min(path.length(), along + 0.6)), behind = path.at(Math.max(0, along - 0.6));
				Vec3 dir = ahead.subtract(behind);
				float yaw = dir.horizontalDistanceSqr() < 1e-6 ? who.heading : (float) (Math.toDegrees(Math.atan2(dir.z, dir.x)) - 90);
				double v = (path.travelled(t + 0.5 / s.fps(), speed, ease) - path.travelled(t - 0.5 / s.fps(), speed, ease)) * s.fps();
				Vec3 tangent = dir.lengthSqr() < 1e-9 ? Vec3.ZERO : dir.normalize().scale(v);
				who.move(at, yaw, new Vec3(tangent.x, 0, tangent.z));
				boolean done = along >= path.length() - 1e-6;
				if (done) {
					who.velocity = Vec3.ZERO;
					if (mark != null) s.mark(mark);
				}
				return done;
			}
		};
	}

	/** A curve through points, sampled densely and measured, so it can be walked at a steady speed. */
	record Path(List<Vec3> samples, double[] lengths) {
		static Path through(List<Vec3> points) {
			List<Vec3> samples = new ArrayList<>();
			for (int i = 0; i < points.size() - 1; i++) {
				Vec3 p0 = points.get(Math.max(0, i - 1)), p1 = points.get(i), p2 = points.get(i + 1), p3 = points.get(Math.min(points.size() - 1, i + 2));
				for (int k = 0; k < 32; k++) samples.add(catmullRom(p0, p1, p2, p3, k / 32.0));
			}
			samples.add(points.getLast());
			double[] lengths = new double[samples.size()];
			for (int i = 1; i < samples.size(); i++) lengths[i] = lengths[i - 1] + samples.get(i).distanceTo(samples.get(i - 1));
			return new Path(samples, lengths);
		}

		double length() { return lengths[lengths.length - 1]; }

		Vec3 at(double along) {
			if (along <= 0) return samples.getFirst();
			if (along >= length()) return samples.getLast();
			int lo = 0, hi = lengths.length - 1;
			while (hi - lo > 1) { int mid = (lo + hi) >>> 1; if (lengths[mid] <= along) lo = mid; else hi = mid; }
			double k = (along - lengths[lo]) / Math.max(1e-9, lengths[hi] - lengths[lo]);
			return samples.get(lo).lerp(samples.get(hi), k);
		}

		/**
		 * Distance covered after {@code t} seconds at {@code speed} with smooth speed-up and slow-down of {@code ease}
		 * seconds each (shorter if the path is too short for both); 0 before the start.
		 */
		double travelled(double t, double speed, double ease) {
			if (t <= 0) return 0;
			double len = length();
			ease = Math.min(ease, len / speed);
			double ramp = speed * ease / 2;
			double cruise = Math.max(0, len - 2 * ramp) / speed;
			if (ease <= 0) return Math.min(len, t * speed);
			if (t < ease) return speed * ease * rampUp(t / ease);
			if (t < ease + cruise) return ramp + (t - ease) * speed;
			double tail = t - ease - cruise;
			if (tail >= ease) return len;
			return len - speed * ease * rampUp(1 - tail / ease);
		}

		/** The distance, in units of speed × ease, covered while speeding up smoothly for {@code k} of the ramp. */
		private static double rampUp(double k) {
			// Speed follows smoothstep(k); its integral is k³ - k⁴/2.
			return k * k * k - k * k * k * k / 2;
		}

		private static Vec3 catmullRom(Vec3 p0, Vec3 p1, Vec3 p2, Vec3 p3, double t) {
			double t2 = t * t, t3 = t2 * t;
			return new Vec3(
				0.5 * (2 * p1.x + (-p0.x + p2.x) * t + (2 * p0.x - 5 * p1.x + 4 * p2.x - p3.x) * t2 + (-p0.x + 3 * p1.x - 3 * p2.x + p3.x) * t3),
				0.5 * (2 * p1.y + (-p0.y + p2.y) * t + (2 * p0.y - 5 * p1.y + 4 * p2.y - p3.y) * t2 + (-p0.y + 3 * p1.y - 3 * p2.y + p3.y) * t3),
				0.5 * (2 * p1.z + (-p0.z + p2.z) * t + (2 * p0.z - 5 * p1.z + 4 * p2.z - p3.z) * t2 + (-p0.z + 3 * p1.z - 3 * p2.z + p3.z) * t3));
		}
	}
}
