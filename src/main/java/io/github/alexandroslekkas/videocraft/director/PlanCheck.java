package io.github.alexandroslekkas.videocraft.director;

import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.ActionType;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.Pose;
import io.github.alexandroslekkas.videocraft.api.RigType;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import io.github.alexandroslekkas.videocraft.plan.Plan;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;
import java.util.function.Function;

/**
 * The whole plan, checked before the world loads, so a typo fails a take in seconds instead of minutes in: every
 * action and rig is known, every actor a cue, rig or position names is staged ({@code [[actor]]}, a {@code stand_in}
 * of the world's staging, or {@code player}), cue times are inside their shot (down to {@code -preroll}), and every
 * rig and action is made once from its parameters against a dry shot, so their own checks run too. A dry shot has no
 * world: anchors are at the origin and actors stand there, and a type that needs the world to be made (anything other
 * than {@link IllegalArgumentException}) is left to its real cue. Types must not change the world when made; that is
 * what {@code frame} is for.
 */
public final class PlanCheck {
	private PlanCheck() {}

	/** Every problem found, each naming its shot and cue; empty if the plan can be played. */
	public static List<String> problems(Plan plan, Function<String, ActionType> actions, Function<String, RigType> rigs, Minecraft mc) {
		List<String> problems = new ArrayList<>();
		Set<String> cast = new LinkedHashSet<>(), standIns = new LinkedHashSet<>();
		cast.add("player");
		for (Plan.ActorSpec a : plan.actors()) cast.add(a.id());
		for (Plan.Cue c : plan.world().stage())
			if (Registries.id(c.action()).equals("videocraft:stand_in") && c.params().has("id")) standIns.add(c.params().string("id"));
		cast.addAll(standIns);
		String preset = plan.world().params().string("preset", "default");
		if (!WorldBoot.PRESETS.contains(preset)) problems.add("world.preset is one of " + WorldBoot.PRESETS + ", not " + preset);
		Dry stage = new Dry("stage", 0, cast, standIns, mc, plan.output().fps());
		for (Plan.Cue c : plan.world().stage()) cue(c, stage, actions, problems, 0, Double.POSITIVE_INFINITY);
		for (Plan.Shot s : plan.shots()) {
			Dry shot = new Dry(s.name(), s.duration(), cast, standIns, mc, plan.output().fps());
			double preroll = s.params().number("preroll", 0);
			try {
				if (s.params().has("weather")) Director.weather(s.params().string("weather"), s.params().where());
				if (preroll < 0 || preroll > 30) throw new IllegalArgumentException(s.params().where() + ": preroll is 0 to 30 seconds, not " + preroll);
				Params camera = s.camera();
				// Rigs look their subjects up frame by frame; a missing one is found here instead.
				if (camera.has("subject")) shot.actor(camera.string("subject"));
				if (camera.has("subjects") && camera.raw("subjects").isJsonArray()) for (String id : camera.strings("subjects")) shot.actor(id);
				make(() -> rigs.apply(camera.string("rig")).create(camera, shot), camera.where());
			} catch (IllegalArgumentException e) {
				problems.add(placed(e, s.camera().where()));
			}
			for (Plan.Cue c : s.timeline()) cue(c, shot, actions, problems, -preroll, s.duration());
		}
		return problems;
	}

	private static void cue(Plan.Cue c, Dry shot, Function<String, ActionType> actions, List<String> problems, double from, double to) {
		String where = c.params().where();
		try {
			if (c.at() < from - 1e-9 || c.at() > to + 1e-9)
				throw new IllegalArgumentException(where + ": at " + c.at() + " is outside the shot (" + (from == 0 ? 0 : from) + " to " + to + " s)");
			if (c.params().has("actor")) shot.actor(c.params().string("actor"));
			ActionType type = actions.apply(c.action());
			// A glide moves a stand-in, which a dry shot has not got: only its subject is checked.
			if (Registries.id(c.action()).equals("videocraft:glide")) {
				String who = c.params().string("actor");
				if (!shot.standIns.contains(who)) throw new IllegalArgumentException(where + ": glide moves a stand_in, and '" + who + "' is not one");
				return;
			}
			make(() -> type.create(c.params(), shot), where);
		} catch (IllegalArgumentException e) {
			problems.add(placed(e, where));
		}
	}

	/** The message, led by where it is in the plan unless it says so itself. */
	private static String placed(IllegalArgumentException e, String where) {
		String m = e.getMessage() == null ? e.toString() : e.getMessage();
		return m.startsWith("shots.") || m.startsWith("world.") || m.startsWith("actors.") ? m : where + ": " + m;
	}

	/** Makes it; a type that cannot be made without a world is skipped (its real cue will say). */
	private static void make(Runnable create, String where) {
		try {
			create.run();
		} catch (IllegalArgumentException e) {
			throw e;
		} catch (RuntimeException e) {
			// Needs the world (a level, an entity, the server): checked for real when its cue comes.
		}
	}

	/** An actor of the dry shot: standing at the origin, facing south. */
	private record Stand(String id) implements Actor {
		@Override public Entity entity() { return null; }
		@Override public Vec3 ground() { return Vec3.ZERO; }
		@Override public Vec3 head() { return new Vec3(0, 1.6, 0); }
	}

	/** A shot without a world. */
	private static final class Dry implements ShotContext {
		private final String name;
		private final double duration;
		private final Set<String> cast, standIns;
		private final Minecraft mc;
		private final int fps;
		private final Random random = new Random(0);

		Dry(String name, double duration, Set<String> cast, Set<String> standIns, Minecraft mc, int fps) {
			this.name = name;
			this.standIns = standIns;
			this.duration = duration;
			this.cast = cast;
			this.mc = mc;
			this.fps = fps;
		}

		@Override public Minecraft minecraft() { return mc; }
		@Override public String shot() { return name; }
		@Override public int frame() { return 0; }
		@Override public double seconds() { return 0; }
		@Override public double duration() { return duration; }
		@Override public boolean recording() { return false; }
		@Override public int fps() { return fps; }
		@Override public Vec3 anchor(String name) { return Vec3.ZERO; }
		@Override public void anchor(String name, Vec3 at) {}
		@Override public Actor actor(String id) {
			if (!cast.contains(id)) throw new IllegalArgumentException("no actor '" + id + "' in this plan; staged: " + cast);
			return new Stand(id);
		}
		@Override public void command(String command) {}
		@Override public void mark(String label) {}
		@Override public void mark(String label, double value) {}
		@Override public Random random() { return random; }
		@Override public Pose camera() { return new Pose(0, 1.6, -4, 0, 0); }
		@Override public void fail(String reason) { throw new IllegalArgumentException(reason); }

		@Override
		public Vec3 position(Params params, String key) {
			var e = params.raw(key);
			if (e == null || e.isJsonNull()) throw new IllegalArgumentException(params.where() + ": missing position '" + key + "'");
			if (e.isJsonArray()) {
				if (e.getAsJsonArray().size() != 3) throw new IllegalArgumentException(params.where() + "." + key + ": a position is [x, y, z]");
				return Vec3.ZERO;
			}
			if (!e.isJsonObject()) throw new IllegalArgumentException(params.where() + "." + key + ": a position is [x, y, z], {anchor = \"name\"} or {actor = \"id\"}");
			var o = e.getAsJsonObject();
			if (o.has("actor")) {
				try {
					actor(o.get("actor").getAsString());
				} catch (IllegalArgumentException x) {
					throw new IllegalArgumentException(params.where() + "." + key + ": " + x.getMessage());
				}
			}
			else if (!o.has("anchor")) throw new IllegalArgumentException(params.where() + "." + key + ": a position table names an anchor or an actor");
			return Vec3.ZERO;
		}
	}
}
