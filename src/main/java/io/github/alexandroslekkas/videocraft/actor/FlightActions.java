package io.github.alexandroslekkas.videocraft.actor;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.api.Action;
import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.Registry;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import net.minecraft.world.entity.decoration.Mannequin;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * The flight actions of the shot script (docs/SCRIPT.md, "Flying actors"): {@code fly}, {@code hover}, {@code swarm},
 * {@code land}. They act on puppets through {@link Flight}; parameters are checked when the cue comes.
 */
final class FlightActions {
	private FlightActions() {}

	static void register(Registry r) {
		r.action("fly", FlightActions::fly);
		r.action("hover", FlightActions::hover);
		r.action("swarm", FlightActions::swarm);
		r.action("land", FlightActions::land);
	}

	private static List<double[]> points(Params params, ShotContext shot) {
		JsonArray list;
		if (params.has("path")) list = params.raw("path").getAsJsonArray();
		else if (params.has("to")) { list = new JsonArray(); list.add(params.raw("to")); }
		else throw new IllegalArgumentException(params.where() + ": fly needs path = [positions] or to = position");
		if (list.isEmpty()) throw new IllegalArgumentException(params.where() + ": path is empty");
		List<double[]> out = new ArrayList<>();
		for (int i = 0; i < list.size(); i++) {
			JsonObject holder = new JsonObject();
			holder.add("p", list.get(i));
			Vec3 v = shot.position(new Params(holder, params.where() + ".path[" + i + "]"), "p");
			out.add(new double[] {v.x, v.y, v.z});
		}
		return out;
	}

	private static double speed(Params params, Puppet p) {
		double speed = params.has("speed") ? params.number("speed") : Flights.speed(p.entityId);
		if (speed <= 0 || speed > 12) throw new IllegalArgumentException(params.where() + ": speed is in blocks per second, 0 to 12");
		return speed;
	}

	private static Action fly(Params params, ShotContext shot) {
		Puppet p = Actions.puppet(params, shot);
		List<double[]> path = points(params, shot);
		double speed = speed(params, p);
		double accel = params.number("accel", 0.45), arrive = params.number("arrive", 0.6), bank = params.number("bank", 1);
		if (bank < 0 || bank > 2) throw new IllegalArgumentException(params.where() + ": bank is 0 (level) to 2 (1 a natural bank)");
		p.follow(null);
		p.flight().fly(path, speed, accel, arrive, bank, new Random(p.random().nextLong()));
		String mark = params.string("mark", null);
		boolean faces = params.has("face");
		if (faces) Actions.yawTo(p, shot, params, "face");
		return new Action() {
			boolean turned;

			@Override
			public boolean frame(ShotContext s) {
				if (!p.hasFlight() || !p.flight().arrived()) return false;
				if (faces && !turned) {
					turned = true;
					p.flight().face(Actions.yawTo(p, s, params, "face"));
				}
				if (mark != null) s.mark(mark);
				return true;
			}
		};
	}

	private static Action hover(Params params, ShotContext shot) {
		Puppet p = Actions.puppet(params, shot);
		Vec3 here = p.feet();
		double[] at = params.has("to") ? vec(shot.position(params, "to")) : new double[] {here.x, here.y, here.z};
		double scale = Math.min(1.5, Math.max(0.35, p.living().getBbWidth() / 0.7));
		double radius = params.number("radius", 0.25 * scale), bob = params.number("bob", 0.06 * scale);
		if (radius < 0 || radius > 4) throw new IllegalArgumentException(params.where() + ": radius (of the drift) is 0 to 4 blocks");
		if (bob < 0 || bob > 1) throw new IllegalArgumentException(params.where() + ": bob is 0 to 1 block");
		double face = params.has("face") ? Actions.yawTo(p, shot, params, "face") : Double.NaN;
		p.follow(null);
		p.flight().hover(at, radius, bob, face, new Random(p.random().nextLong()));
		double seconds = params.number("seconds", 0);
		double start = p.time();
		String mark = params.string("mark", null);
		return s -> {
			if (p.time() - start < seconds) return false;
			if (mark != null) s.mark(mark);
			return true;
		};
	}

	private static double[] vec(Vec3 v) { return new double[] {v.x, v.y, v.z}; }

	private static Action swarm(Params params, ShotContext shot) {
		List<Puppet> bees = new ArrayList<>();
		if (params.has("bees")) {
			for (String id : params.strings("bees")) {
				JsonObject o = new JsonObject();
				o.addProperty("actor", id);
				o.addProperty("do", "swarm");
				bees.add(Actions.puppet(new Params(o, params.where()), shot));
			}
		} else bees.add(Actions.puppet(params, shot));
		if (bees.isEmpty()) throw new IllegalArgumentException(params.where() + ": swarm needs bees = [actor ids] (or actor)");
		JsonElement around = params.raw("around");
		if (around == null) throw new IllegalArgumentException(params.where() + ": swarm needs around = an actor id or a position");
		Flights.ActorAnchor anchor = null;
		double[] point = null;
		double height;
		if (around.isJsonPrimitive() && around.getAsJsonPrimitive().isString()) {
			Actor a = shot.actor(around.getAsString());
			for (Puppet b : bees) if (b == a) throw new IllegalArgumentException(params.where() + ": a bee cannot swarm round itself");
			anchor = new Flights.ActorAnchor(a);
			height = anchor.height();
		} else {
			point = vec(shot.position(params, "around"));
			height = 0;
		}
		double lift = params.number("lift", anchor == null ? 0 : height * 0.55);
		double speed = params.number("speed", 2.4);
		if (speed <= 0 || speed > 10) throw new IllegalArgumentException(params.where() + ": speed is 0 to 10 blocks per second");
		Flight lead = bees.getFirst().flight();
		double width = anchor == null ? 0 : anchor.width();
		double inner = params.number("radius", 0), outer = params.number("outer", 0);
		double[] lanes = lead.lanes(bees.size(), width, inner, outer);
		double gap = lanes.length > 1 ? lanes[1] - lanes[0] : 0.6;
		Boolean angry = params.has("angry") ? params.bool("angry", false) : null;
		for (int i = 0; i < bees.size(); i++) {
			Puppet b = bees.get(i);
			if (angry != null) b.angry(angry);
			b.follow(anchor);
			b.flight().orbit(anchor, point, lanes[i], lift, speed, gap, new Random(b.random().nextLong()));
		}
		String mark = params.string("mark", null);
		if (mark != null) shot.mark(mark);
		double seconds = params.number("seconds", 0);
		double start = bees.getFirst().time();
		return s -> bees.getFirst().time() - start >= seconds;
	}

	private static Action land(Params params, ShotContext shot) {
		Puppet p = Actions.puppet(params, shot);
		JsonElement on = params.raw("on");
		if (on == null) throw new IllegalArgumentException(params.where() + ": land needs on = an actor id or a position");
		double speed = params.number("speed", Math.min(2.2, Flights.speed(p.entityId)));
		if (speed <= 0 || speed > 12) throw new IllegalArgumentException(params.where() + ": speed is in blocks per second, 0 to 12");
		Flight f = p.flight();
		if (on.isJsonPrimitive() && on.getAsJsonPrimitive().isString()) {
			Actor a = shot.actor(on.getAsString());
			if (a == p) throw new IllegalArgumentException(params.where() + ": an actor cannot land on itself");
			Flights.ActorAnchor anchor = new Flights.ActorAnchor(a);
			double[] local = spot(params, a, anchor);
			p.follow(anchor);
			f.land(anchor, local, null, speed, new Random(p.random().nextLong()));
		} else {
			Vec3 at = shot.position(params, "on");
			double g = p.groundAt(at.x, at.z, at.y, true);
			p.follow(null);
			f.land(null, null, new double[] {at.x, Double.isNaN(g) ? at.y : g, at.z}, speed, new Random(p.random().nextLong()));
		}
		String mark = params.string("mark", null);
		return s -> {
			if (p.flying()) return false;
			if (mark != null) s.mark(mark);
			return true;
		};
	}

	/**
	 * Where on an actor a flyer lands, {front, right, up} from its feet: a player-shaped body's shoulder (the `side`,
	 * right by default), another body's back; `front`, `right`, `up` move it.
	 */
	private static double[] spot(Params params, Actor a, Flights.ActorAnchor anchor) {
		double h = anchor.height(), s = h / 1.8;
		boolean humanoid = a.entity() instanceof Mannequin || a.entity() instanceof Player;
		String side = params.string("side", "right");
		if (!side.equals("right") && !side.equals("left")) throw new IllegalArgumentException(params.where() + ": side is right or left");
		double sign = side.equals("right") ? 1 : -1;
		// A player model's shoulder top is 24 of its 32 pixels up (drawn 0.9375 high), the arm's middle 6 pixels out.
		double front = params.number("front", 0), right = params.number("right", humanoid ? sign * 0.34 * s : 0);
		double up = params.number("up", humanoid ? 1.41 * s : h);
		return new double[] {front, right, up};
	}
}
