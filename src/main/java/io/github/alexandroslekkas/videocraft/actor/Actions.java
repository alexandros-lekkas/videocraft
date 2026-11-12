package io.github.alexandroslekkas.videocraft.actor;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.api.Action;
import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.Registry;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.sounds.SoundEvents;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.animal.chicken.Chicken;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.component.SwingAnimation;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * The actor actions of the shot script (docs/SCRIPT.md, "Actors"). Each validates its parameters when its cue comes
 * and fails the take with the script location otherwise. They act on puppets ({@code kind = "mob"} or {@code
 * * "mannequin"} actors) and, for walk, turn, look, jump, crouch and swing, on the played player.
 */
public final class Actions {
	private Actions() {}

	public static void register(Registry r) {
		r.action("place", Actions::place);
		r.action("walk", (p, s) -> walk(p, s, null));
		r.action("run", (p, s) -> walk(p, s, "run"));
		r.action("stop", Actions::stop);
		r.action("turn", Actions::turn);
		r.action("look", Actions::look);
		r.action("hop", Actions::hop);
		r.action("jump", Actions::hop);
		r.action("state", Actions::state);
		r.action("crouch", (p, s) -> namedState(p, s, "crouch"));
		r.action("hold", Actions::hold);
		r.action("emit", Actions::emit);
		r.action("voice", Actions::voice);
		r.action("swing", Actions::swing);
		r.action("nod", (p, s) -> gesture(p, s, Gesture.Kind.NOD, 0.85));
		r.action("shake", (p, s) -> gesture(p, s, Gesture.Kind.SHAKE, 1.1));
		r.action("talk", (p, s) -> gesture(p, s, Gesture.Kind.TALK, 2.0));
		r.action("point", (p, s) -> gesture(p, s, Gesture.Kind.POINT, Double.POSITIVE_INFINITY));
		r.action("pose", Actions::pose);
		r.action("blink", (p, s) -> {
			throw new IllegalArgumentException(p.where() + ": blink: no vanilla mob or mannequin model has eyelids to close; use a nod or a look instead");
		});
	}

	static Puppet puppet(Params p, ShotContext shot) {
		String id = p.string("actor", "player");
		Actor a = shot.actor(id);
		if (a instanceof Puppet puppet) {
			if (puppet.living() == null) puppet.frame(shot);
			return puppet;
		}
		throw new IllegalArgumentException(p.where() + ": '" + p.string("do") + "' needs a staged actor (kind = \"mob\" or \"mannequin\"); '" + id + "' is the played player, who can walk, run, stop, turn, look, jump, crouch and swing");
	}

	private static Action done() { return s -> true; }

	/** The played player, when the cue is for it (actor = "player", the default). */
	static PlayerActor player(Params p, ShotContext shot) {
		return shot.actor(p.string("actor", "player")) instanceof PlayerActor player ? player : null;
	}

	private static List<Vec3> positions(Params params, ShotContext shot) {
		List<Vec3> out = new ArrayList<>();
		JsonArray list = params.has("path") ? params.raw("path").getAsJsonArray() : new JsonArray();
		if (!params.has("path") && params.has("to")) list.add(params.raw("to"));
		if (list.isEmpty()) throw new IllegalArgumentException(params.where() + ": walk needs path = [positions] or to = position");
		for (int i = 0; i < list.size(); i++) {
			JsonObject holder = new JsonObject();
			holder.add("p", list.get(i));
			out.add(shot.position(new Params(holder, params.where() + ".path[" + i + "]"), "p"));
		}
		return out;
	}

	/** A heading as a point to look at: a target, or a number of degrees turned into a point ahead at eye level. */
	private static Vec3 lookPoint(PlayerActor pl, ShotContext shot, Params params, String key) {
		JsonElement e = params.raw(key);
		if (e != null && e.isJsonPrimitive() && e.getAsJsonPrimitive().isNumber()) {
			double yaw = Math.toRadians(e.getAsDouble());
			Vec3 eye = pl.entity().getEyePosition();
			return eye.add(-Math.sin(yaw) * 10, 0, Math.cos(yaw) * 10);
		}
		return point(shot, params, key);
	}

	// ---- Where things are ----

	/** A target as a point: an actor id (its head), "camera" (the lens), or a position. */
	static Vec3 point(ShotContext shot, Params params, String key) {
		JsonElement e = params.raw(key);
		if (e == null || e.isJsonNull()) throw new IllegalArgumentException(params.where() + ": missing '" + key + "'");
		if (e.isJsonPrimitive() && e.getAsJsonPrimitive().isString()) {
			String name = e.getAsString();
			if (name.equals("camera")) return shot.minecraft().gameRenderer.mainCamera().position();
			return shot.actor(name).head();
		}
		return shot.position(params, key);
	}

	/** A heading: a number of degrees (Minecraft yaw), or the direction from the puppet toward a target. */
	static double yawTo(Puppet p, ShotContext shot, Params params, String key) {
		JsonElement e = params.raw(key);
		if (e != null && e.isJsonPrimitive() && e.getAsJsonPrimitive().isNumber()) return e.getAsDouble();
		Vec3 to = point(shot, params, key), from = p.ground();
		if (Math.hypot(to.x - from.x, to.z - from.z) < 1e-3) return p.heading();
		return Path.yaw(to.x - from.x, to.z - from.z);
	}

	private static List<double[]> points(Params params, ShotContext shot) {
		List<double[]> out = new ArrayList<>();
		JsonArray list;
		if (params.has("path")) list = params.raw("path").getAsJsonArray();
		else if (params.has("to")) { list = new JsonArray(); list.add(params.raw("to")); }
		else throw new IllegalArgumentException(params.where() + ": walk needs path = [positions] or to = position");
		if (list.isEmpty()) throw new IllegalArgumentException(params.where() + ": path is empty");
		for (int i = 0; i < list.size(); i++) {
			JsonObject holder = new JsonObject();
			holder.add("p", list.get(i));
			Vec3 v = shot.position(new Params(holder, params.where() + ".path[" + i + "]"), "p");
			out.add(new double[] {v.x, v.z});
		}
		return out;
	}

	// ---- Actions ----

	private static Action place(Params params, ShotContext shot) {
		Puppet p = puppet(params, shot);
		// `at` is the cue's time, so the place is `to`.
		Vec3 at = shot.position(params, "to");
		double yaw = params.has("facing") ? facing(p, shot, params, at) : p.heading();
		p.place(at, yaw);
		return done();
	}

	static double facing(Puppet p, ShotContext shot, Params params, Vec3 at) {
		JsonElement e = params.raw("facing");
		if (e.isJsonPrimitive() && e.getAsJsonPrimitive().isNumber()) return e.getAsDouble();
		Vec3 to = point(shot, params, "facing");
		return Path.yaw(to.x - at.x, to.z - at.z);
	}

	private static Action walk(Params params, ShotContext shot, String forced) {
		PlayerActor pl = player(params, shot);
		if (pl != null) {
			String gait = forced != null ? forced : params.string("gait", "walk");
			boolean sprint = params.bool("sprint", gait.equals("run"));
			pl.walk(positions(params, shot), sprint, params.has("face") ? point(shot, params, "face") : null);
			String mark = params.string("mark", null);
			return s -> {
				if (pl.walking()) return false;
				if (mark != null) s.mark(mark);
				return true;
			};
		}
		Puppet p = puppet(params, shot);
		String gait = forced != null ? forced : params.string("gait", "walk").toLowerCase(Locale.ROOT);
		double speed = params.has("speed") ? params.number("speed") : p.breed().pace(gait, params.where());
		if (speed <= 0 || speed > 8) throw new IllegalArgumentException(params.where() + ": speed is in blocks per second, 0 to 8");
		if (!params.has("speed") && gait.equals("walk") && params.bool("strut", false)) gait = "strut";
		double accel = params.number("accel", gait.equals("run") ? 0.5 : 0.35);
		double arrive = params.number("arrive", gait.equals("run") ? 0.6 : 0.5);
		List<double[]> path = points(params, shot);
		p.walk(path, speed, gait, accel, arrive);
		String mark = params.string("mark", null);
		boolean faces = params.has("face");
		return new Action() {
			boolean turned;

			@Override
			public boolean frame(ShotContext s) {
				if (p.walking()) return false;
				if (faces && !turned) {
					turned = true;
					p.turn(yawTo(p, s, params, "face"), 1);
				}
				if (mark != null) s.mark(mark);
				return true;
			}
		};
	}

	private static Action stop(Params params, ShotContext shot) {
		PlayerActor pl = player(params, shot);
		if (pl != null) { pl.stop(); return done(); }
		Puppet p = puppet(params, shot);
		p.halt(params.number("arrive", 0.35));
		return s -> !p.walking();
	}

	private static Action turn(Params params, ShotContext shot) {
		PlayerActor pl = player(params, shot);
		if (pl != null) {
			pl.turnTo(lookPoint(pl, shot, params, "to"), params.number("tolerance", 0.6));
			String mark = params.string("mark", null);
			return new Action() {
				int frames;

				@Override
				public boolean frame(ShotContext s) {
					if (++frames < 4 || pl.turning()) return false;
					if (mark != null) s.mark(mark);
					return true;
				}
			};
		}
		Puppet p = puppet(params, shot);
		double pace = params.number("pace", 1);
		if (pace <= 0 || pace > 4) throw new IllegalArgumentException(params.where() + ": pace is 0 to 4 (1 a calm turn)");
		boolean follow = params.bool("follow", false);
		p.turn(yawTo(p, shot, params, "to"), pace);
		String mark = params.string("mark", null);
		return new Action() {
			int frames;

			@Override
			public boolean frame(ShotContext s) {
				frames++;
				if (follow) { p.retarget(yawTo(p, s, params, "to")); return false; }
				if (frames < 6 || p.turning()) return false;
				if (mark != null) s.mark(mark);
				return true;
			}
		};
	}

	private static Action look(Params params, ShotContext shot) {
		PlayerActor pl = player(params, shot);
		if (pl != null) {
			double hold = params.number("hold", Double.POSITIVE_INFINITY);
			pl.turnTo(point(shot, params, "target"), 1.5);
			return new Action() {
				int frames;

				@Override
				public boolean frame(ShotContext s) {
					frames++;
					if (frames / (double) s.fps() >= hold) return true;
					if (!pl.turning()) pl.follow(point(s, params, "target"));
					return false;
				}
			};
		}
		Puppet p = puppet(params, shot);
		double hold = params.number("hold", Double.POSITIVE_INFINITY);
		boolean back = params.bool("back", !Double.isInfinite(hold));
		point(shot, params, "target");
		double start = p.time();
		return new Action() {
			@Override
			public boolean frame(ShotContext s) {
				if (p.time() - start >= hold) {
					if (back) p.lookBack();
					return true;
				}
				Vec3 eye = p.head(), to = point(s, params, "target");
				double dx = to.x - eye.x, dz = to.z - eye.z;
				p.look(Path.yaw(dx, dz), -Math.toDegrees(Math.atan2(to.y - eye.y, Math.hypot(dx, dz))));
				return false;
			}

			@Override
			public void stop(ShotContext s) { if (back) p.lookBack(); }
		};
	}

	private static Action hop(Params params, ShotContext shot) {
		PlayerActor pl = player(params, shot);
		if (pl != null) { pl.jump(); return done(); }
		Puppet p = puppet(params, shot);
		double height = params.number("height", 0.55), seconds = params.number("seconds", 0.2 + 0.3 * Math.sqrt(height));
		if (height <= 0 || height > 3) throw new IllegalArgumentException(params.where() + ": height is 0 to 3 blocks");
		p.hop(height, seconds);
		return done();
	}

	private static Action state(Params params, ShotContext shot) {
		return namedState(params, shot, params.string("state"));
	}

	private static Action namedState(Params params, ShotContext shot, String name) {
		PlayerActor pl = player(params, shot);
		if (pl != null) {
			if (!name.equals("crouch") && !name.equals("sneak")) throw new IllegalArgumentException(params.where() + ": the player's states are crouch (sneak); '" + name + "' is a puppet's");
			boolean on = params.bool("on", true);
			pl.sneak(on);
			double seconds = params.number("seconds", Double.NaN);
			if (Double.isNaN(seconds)) return done();
			int[] frames = {0};
			return s -> {
				if (++frames[0] / (double) s.fps() < seconds) return false;
				pl.sneak(!on);
				return true;
			};
		}
		Puppet p = puppet(params, shot);
		boolean on = params.bool("on", true);
		double seconds = params.number("seconds", Double.NaN);
		if (name.equals("flap")) {
			p.flap(Double.isNaN(seconds) ? 0.6 : seconds);
			return done();
		}
		p.state(name, on, params.where());
		if (Double.isNaN(seconds)) return done();
		double start = p.time();
		return new Action() {
			@Override
			public boolean frame(ShotContext s) {
				if (p.time() - start < seconds) return false;
				p.state(name, !on, params.where());
				return true;
			}

			@Override
			public void stop(ShotContext s) { p.state(name, !on, params.where()); }
		};
	}

	private static ItemStack item(Params params, String key, String fallback) {
		String id = params.string(key, fallback);
		if (id == null) throw new IllegalArgumentException(params.where() + ": missing '" + key + "' (an item id such as minecraft:egg)");
		if (id.isEmpty() || id.equals("none")) return ItemStack.EMPTY;
		var item = BuiltInRegistries.ITEM.getOptional(Identifier.parse(id));
		if (item.isEmpty() || item.get() == Items.AIR) throw new IllegalArgumentException(params.where() + ": no item '" + id + "'");
		return new ItemStack(item.get(), (int) params.number("count", 1));
	}

	private static Action hold(Params params, ShotContext shot) {
		Puppet p = puppet(params, shot);
		String hand = params.string("hand", "main");
		if (!hand.equals("main") && !hand.equals("off")) throw new IllegalArgumentException(params.where() + ": hand is main or off");
		p.hold(item(params, "item", null), hand.equals("off"));
		return done();
	}

	private static Action emit(Params params, ShotContext shot) {
		Puppet p = puppet(params, shot);
		boolean chicken = p.living() instanceof Chicken;
		ItemStack stack = item(params, "item", chicken ? "minecraft:egg" : null);
		double up = params.number("pop", 2.4), side = params.number("side", (p.random().nextBoolean() ? 1 : -1) * (0.1 + p.random().nextDouble() * 0.12));
		double yaw = Math.toRadians(p.heading()), back = 0.7;
		p.emit(stack, new Vec3(Math.sin(yaw) * back, up, -Math.cos(yaw) * back), side);
		String sound = params.string("sound", chicken ? "minecraft:entity.chicken.egg" : "minecraft:entity.item.pickup");
		if (!sound.equals("none")) {
			float pitch = (float) params.number("pitch", (p.random().nextFloat() - p.random().nextFloat()) * 0.2 + 1);
			p.play(p.sound(sound, params.where()), (float) params.number("volume", 1), pitch);
		}
		return done();
	}

	private static Action voice(Params params, ShotContext shot) {
		Puppet p = puppet(params, shot);
		var sound = p.sound(params.string("sound", "ambient"), params.where());
		float volume = (float) params.number("volume", p.soundVolume());
		// Vanilla's voice pitch formula, but drawn from the take's seed (the entity's own random is not), so takes match.
		float vanilla = (p.random().nextFloat() - p.random().nextFloat()) * 0.2f + (p.living().isBaby() ? 1.5f : 1f);
		float pitch = (float) params.number("pitch", vanilla);
		p.play(sound, volume, pitch);
		return done();
	}

	private static Action swing(Params params, ShotContext shot) {
		PlayerActor pl = player(params, shot);
		if (pl != null) { pl.swing(); return done(); }
		Puppet p = puppet(params, shot);
		String hand = params.string("hand", "main");
		p.living().swing(hand.equals("off") ? InteractionHand.OFF_HAND : InteractionHand.MAIN_HAND, SwingAnimation.DEFAULT, false);
		return done();
	}

	private static Action gesture(Params params, ShotContext shot, Gesture.Kind kind, double length) {
		Puppet p = puppet(params, shot);
		if (kind.arms() && !p.kind.equals("mannequin")) throw new IllegalArgumentException(params.where() + ": " + kind.name().toLowerCase(Locale.ROOT) + " needs arms: a mannequin actor");
		double seconds = params.number("seconds", length), size = params.number("size", 1);
		// One arm pose at a time: a new one takes over from the last as it eases in.
		if (kind.arms()) for (Gesture g : p.gestures) if (g.kind.arms() && Double.isNaN(g.release)) g.release = p.time();
		p.gesture(new Gesture(kind, p.time(), seconds, size, p.random().nextInt(1000)));
		return done();
	}

	private static Action pose(Params params, ShotContext shot) {
		Puppet p = puppet(params, shot);
		String name = params.string("pose").toLowerCase(Locale.ROOT);
		switch (name) {
			case "sit", "crouch", "sleep" -> { return namedState(params, shot, name); }
			case "none", "stand" -> {
				for (Gesture g : p.gestures) if (g.kind.arms() && Double.isNaN(g.release)) g.release = p.time();
				for (String s : new String[] {"sit", "crouch", "sleep"}) if (p.has(s)) p.state(s, false, params.where());
				return done();
			}
			default -> { return gesture(params, shot, Gesture.Kind.of(name, params.where()), Double.POSITIVE_INFINITY); }
		}
	}
}
