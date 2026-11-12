package io.github.alexandroslekkas.videocraft.camera;

import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.CameraRig;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.Pose;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import io.github.alexandroslekkas.videocraft.api.View;
import net.minecraft.world.phys.Vec3;

import java.util.List;

/**
 * The rigs that film someone: an unseen operator who follows a subject's ground point through {@link Follow} (so a
 * jump or a step never bobs the camera), keeps out of blocks ({@link Probe}), and shares the lens and handheld drift
 * of {@link Lens}. Each is documented in docs/SCRIPT.md, "Camera rigs"; the numbers there are the defaults here.
 */
final class Moves {
	private Moves() {}

	/** How close a wall may come to the lens before the camera is pulled in front of it. */
	static final double MARGIN = 0.3;

	static double range(Params p, String key, double fallback, double min, double max) {
		double v = p.number(key, fallback);
		if (v < min || v > max) throw new IllegalArgumentException(p.where() + ": " + key + " is " + min + " to " + max + ", not " + v);
		return v;
	}

	/** Seconds into the shot as a fraction of it, 0 to 1 (0 through pre-roll). */
	static double progress(ShotContext shot) {
		return shot.duration() <= 0 ? 0 : Math.max(0, Math.min(1, shot.seconds() / shot.duration()));
	}

	/** A camera at {@code eye} looking at {@code at}, with the lens's handheld wander added. */
	static Pose look(Vec3 eye, Vec3 at, Lens lens, ShotContext shot) {
		Pose p = Pose.looking(eye, at);
		return lens.drift == 0 ? p : new Pose(p.x(), p.y(), p.z(), (float) (p.yaw() + lens.yaw(shot.seconds())), (float) (p.pitch() + lens.pitch(shot.seconds())));
	}

	/**
	 * Keeps a camera that hangs off a subject out of the blocks between them: the line from {@code pivot} (on the
	 * subject) to the wanted eye is probed now and where the subject will be in half a second, the camera comes in
	 * quickly in front of whatever is in the way and goes back out slowly, and rises a little if it would have to come
	 * very close. Smoothed, so a lamp post never makes it jump.
	 */
	static final class Reach {
		private final Operator op = new Operator(2);
		private final double minimum;
		private double at = Double.NaN;

		Reach(double minimum) { this.minimum = minimum; }

		Vec3 eye(Probe probe, Vec3 pivot, Vec3 want, Vec3 velocity, ShotContext shot) {
			Vec3 arm = want.subtract(pivot);
			double length = arm.length();
			if (length < 1e-6) return want;
			// Probed a margin past the wanted eye, so the distance allowed is continuous: in the open it is exactly the
			// arm, and a wall coming into range pulls it in smoothly instead of by a step of the margin.
			Vec3 reach = arm.scale((length + MARGIN) / length), ahead = pivot.add(velocity.scale(0.5));
			double free = Math.min(probe.free(pivot, pivot.add(reach)), probe.free(ahead, ahead.add(reach)));
			double allowed = Math.max(0.2, Math.min(length, free - MARGIN));
			double rise = allowed < minimum ? Math.min(2.0, (minimum - allowed) * 0.8) : 0;
			double lag = !Double.isNaN(at) && allowed < at ? 0.25 : 0.6;
			double[] r = op.follow(new double[] {allowed, rise}, lag, 1.0 / shot.fps());
			at = r[0];
			return pivot.add(arm.scale(r[0] / length)).add(0, r[1], 0);
		}
	}

	// ---- lead: in front of a subject walking toward the lens ----

	/**
	 * The benchmark's lead track: the camera travels backwards in front of a subject walking towards it, about head
	 * height, pitched a little down, on a wide lens; the subject stays centred and the same size while the set flows
	 * past. The camera stays on the subject's smoothed heading; with {@code swing} it also arcs round when the subject
	 * turns where it stands. {@code yaw_drift} swings the camera round the subject by that many degrees over the shot.
	 */
	static final class Lead implements CameraRig {
		final Follow follow;
		final Lens lens;
		final double distance, height, pitch, side, yawDrift;
		final Reach reach;

		Lead(Params p, ShotContext shot) {
			boolean swing = p.bool("swing", false);
			follow = Follow.of(p, 0.25, swing ? 0.6 : 1.2, swing);
			distance = range(p, "distance", 4, 0.5, 64);
			height = range(p, "height", 1.0, -4, 32);
			pitch = range(p, "pitch", 5, -60, 80);
			side = range(p, "side", 0, -16, 16);
			yawDrift = range(p, "yaw_drift", 0, -180, 180);
			lens = new Lens(p, 105, shot);
			reach = new Reach(Math.min(1.5, distance));
		}

		@Override public View view() { return View.CAMERA; }
		@Override public int fov() { return lens.start(); }
		@Override public double fov(ShotContext shot) { return lens.fov(shot); }
		@Override public String subject() { return follow.subject; }

		@Override
		public Pose pose(ShotContext shot, float partialTick) {
			follow.update(shot);
			double axis = follow.heading() + yawDrift * Rigs.ease("smooth", progress(shot));
			Vec3 g = follow.anchor(), pivot = g.add(0, height, 0);
			Vec3 want = pivot.add(Follow.forward(axis).scale(distance)).add(Follow.right(axis).scale(-side));
			Vec3 eye = reach.eye(Rigs.probe, pivot, want, follow.velocity(), shot);
			// Aimed at the subject sideways, at a fixed tilt: the horizon stays still while the street goes by.
			double yaw = Math.toDegrees(Math.atan2(g.z - eye.z, g.x - eye.x)) - 90;
			return new Pose(eye.x, eye.y, eye.z, (float) (yaw + lens.yaw(shot.seconds())), (float) (pitch + lens.pitch(shot.seconds())));
		}
	}

	// ---- chase and track: behind and beside ----

	/** Behind the subject, a little above it, looking at it over its shoulder. */
	static final class Chase implements CameraRig {
		final Follow follow;
		final Lens lens;
		final double distance, height, look, side;
		final Reach reach;

		Chase(Params p, ShotContext shot) {
			follow = Follow.of(p, 0.3, 0.8, false);
			distance = range(p, "distance", 4, 0.5, 64);
			height = range(p, "height", 1.6, -4, 32);
			look = range(p, "look", 1.0, -4, 8);
			side = range(p, "side", 0, -16, 16);
			lens = new Lens(p, 70, shot);
			reach = new Reach(Math.min(1.5, distance));
		}

		@Override public View view() { return View.CAMERA; }
		@Override public int fov() { return lens.start(); }
		@Override public double fov(ShotContext shot) { return lens.fov(shot); }
		@Override public String subject() { return follow.subject; }

		@Override
		public Pose pose(ShotContext shot, float partialTick) {
			follow.update(shot);
			double axis = follow.heading();
			Vec3 g = follow.anchor(), target = g.add(0, look, 0), pivot = g.add(0, height, 0);
			Vec3 want = pivot.add(Follow.forward(axis).scale(-distance)).add(Follow.right(axis).scale(side));
			return look(reach.eye(Rigs.probe, pivot, want, follow.velocity(), shot), target, lens, shot);
		}
	}

	/**
	 * Alongside the subject, the camera moving parallel to its way: {@code side} is "left" or "right" of the subject,
	 * {@code ahead} moves the camera forward along the way (negative: behind).
	 */
	static final class Track implements CameraRig {
		final Follow follow;
		final Lens lens;
		final double distance, height, look, ahead, sign;
		final Reach reach;

		Track(Params p, ShotContext shot) {
			follow = Follow.of(p, 0.3, 1.5, false);
			distance = range(p, "distance", 4, 0.5, 64);
			height = range(p, "height", 1.2, -4, 32);
			look = range(p, "look", 0.9, -4, 8);
			ahead = range(p, "ahead", 0, -16, 16);
			String side = p.string("side", "right");
			if (!side.equals("left") && !side.equals("right")) throw new IllegalArgumentException(p.where() + ": side is left or right, not " + side);
			sign = side.equals("right") ? 1 : -1;
			lens = new Lens(p, 70, shot);
			reach = new Reach(Math.min(1.5, distance));
		}

		@Override public View view() { return View.CAMERA; }
		@Override public int fov() { return lens.start(); }
		@Override public double fov(ShotContext shot) { return lens.fov(shot); }
		@Override public String subject() { return follow.subject; }

		@Override
		public Pose pose(ShotContext shot, float partialTick) {
			follow.update(shot);
			double axis = follow.heading();
			Vec3 g = follow.anchor(), pivot = g.add(0, height, 0);
			Vec3 want = pivot.add(Follow.right(axis).scale(sign * distance)).add(Follow.forward(axis).scale(ahead));
			Vec3 eye = reach.eye(Rigs.probe, pivot, want, follow.velocity(), shot);
			return look(eye, g.add(Follow.forward(axis).scale(ahead * 0.5)).add(0, look, 0), lens, shot);
		}
	}

	// ---- dolly, crane, locked: an eye on its own path, looking at a point or a subject ----

	/** What a camera on its own path looks at: a fixed {@code at} position, or a {@code subject} followed with lag. */
	static final class Aim {
		final Vec3 point;
		final Follow follow;
		final double look;

		Aim(Params p, ShotContext shot, double lag) {
			if (p.has("subject")) {
				follow = Follow.of(p, lag, 1.0, false);
				point = null;
			} else if (p.has("at")) {
				follow = null;
				point = shot.position(p, "at");
			} else {
				throw new IllegalArgumentException(p.where() + ": give at (a position) or subject (an actor id) to look at");
			}
			look = range(p, "look", 1.0, -4, 8);
		}

		Vec3 target(ShotContext shot) {
			if (follow == null) return point;
			follow.update(shot);
			return follow.anchor().add(0, look, 0);
		}

		String subject() { return follow == null ? null : follow.subject; }
	}

	/** The eye goes from {@code from} to {@code to} over the shot ({@code ease}), looking at {@code at} or a {@code subject}. */
	static final class Dolly implements CameraRig {
		final Vec3 from, to;
		final String ease;
		final Aim aim;
		final Lens lens;

		Dolly(Params p, ShotContext shot) {
			from = shot.position(p, "from");
			to = shot.position(p, "to");
			ease = p.string("ease", "smooth");
			Rigs.ease(ease, 0);
			aim = new Aim(p, shot, p.number("lag", 0.4));
			lens = new Lens(p, 70, shot);
		}

		Dolly(Vec3 from, Vec3 to, String ease, Aim aim, Lens lens) {
			this.from = from;
			this.to = to;
			this.ease = ease;
			this.aim = aim;
			this.lens = lens;
		}

		@Override public View view() { return View.CAMERA; }
		@Override public int fov() { return lens.start(); }
		@Override public double fov(ShotContext shot) { return lens.fov(shot); }
		@Override public String subject() { return aim.subject(); }

		@Override
		public Pose pose(ShotContext shot, float partialTick) {
			Vec3 eye = from.lerp(to, Rigs.ease(ease, progress(shot)));
			return look(eye, aim.target(shot), lens, shot);
		}
	}

	/** A crane: from {@code eye}, rises by {@code rise} blocks (negative: comes down), or moves to {@code to}, looking all the while. */
	static CameraRig crane(Params p, ShotContext shot) {
		Vec3 eye = shot.position(p, "eye");
		Vec3 to = p.has("to") ? shot.position(p, "to") : eye.add(0, range(p, "rise", 3, -64, 64), 0);
		String ease = p.string("ease", "smooth");
		Rigs.ease(ease, 0);
		return new Dolly(eye, to, ease, new Aim(p, shot, p.number("lag", 0.4)), new Lens(p, 70, shot));
	}

	/** A camera on a tripod at {@code eye} that pans and tilts to keep a subject, trailing it by {@code lag}. */
	static CameraRig locked(Params p, ShotContext shot) {
		Vec3 eye = shot.position(p, "eye");
		if (!p.has("subject")) throw new IllegalArgumentException(p.where() + ": locked follows a subject (an actor id)");
		return new Dolly(eye, eye, "linear", new Aim(p, shot, p.number("lag", 0.5)), new Lens(p, 70, shot));
	}

	// ---- two_shot: two subjects in one frame ----

	/**
	 * Two subjects side by side in frame: the camera stands off the line between them (on {@code side} 1 or -1 of the
	 * line from the first to the second) far enough that both fit with room around them, and moves as they do.
	 */
	static final class TwoShot implements CameraRig {
		final Follow a, b;
		final Lens lens;
		final double height, look, margin, minimum, sign, aspect;
		final Operator reach = new Operator(1), normal = new Operator(2);
		final Reach clear = new Reach(1.5);

		TwoShot(Params p, ShotContext shot) {
			List<String> ids = p.strings("subjects");
			if (ids.size() != 2) throw new IllegalArgumentException(p.where() + ": subjects = [\"<actor>\", \"<actor>\"], two of them");
			double lag = range(p, "lag", 0.4, 0, 5);
			a = new Follow(ids.get(0), lag, 1.0, false);
			b = new Follow(ids.get(1), lag, 1.0, false);
			height = range(p, "height", 1.4, -4, 32);
			look = range(p, "look", 0.8, -4, 8);
			margin = range(p, "margin", 1.0, 0, 16);
			minimum = range(p, "min_distance", 2.5, 0.5, 64);
			sign = range(p, "side", 1, -1, 1) >= 0 ? 1 : -1;
			aspect = range(p, "aspect", 16.0 / 9, 0.3, 4);
			lens = new Lens(p, 60, shot);
		}

		@Override public View view() { return View.CAMERA; }
		@Override public int fov() { return lens.start(); }
		@Override public double fov(ShotContext shot) { return lens.fov(shot); }
		@Override public String subject() { return a.subject; }

		@Override
		public Pose pose(ShotContext shot, float partialTick) {
			a.update(shot);
			b.update(shot);
			double dt = 1.0 / shot.fps();
			Vec3 pa = a.anchor(), pb = b.anchor(), mid = pa.lerp(pb, 0.5);
			Vec3 line = new Vec3(pb.x - pa.x, 0, pb.z - pa.z);
			double separation = line.length();
			if (separation < 1e-3) line = Follow.right(a.heading());
			Vec3 n = new Vec3(-line.z, 0, line.x).normalize().scale(sign);
			double[] nn = normal.follow(new double[] {n.x, n.z}, 1.0, dt);
			n = new Vec3(nn[0], 0, nn[1]).normalize();
			double half = Math.toRadians(lens.fov(shot)) / 2, wide = Math.atan(Math.tan(half) * aspect);
			double want = Math.max(minimum, (separation / 2 + margin) / (Math.tan(wide) * 0.8));
			double d = reach.follow(new double[] {want}, 0.6, dt)[0];
			Vec3 pivot = mid.add(0, height, 0);
			Vec3 eye = clear.eye(Rigs.probe, pivot, pivot.add(n.scale(d)), a.velocity().add(b.velocity()).scale(0.5), shot);
			return look(eye, mid.add(0, look, 0), lens, shot);
		}
	}

	// ---- face: the close-up ----

	/**
	 * A close-up of a subject's face: {@code distance} in front of its head on its heading, {@code angle} degrees off
	 * that axis (positive: round to the subject's right), {@code height} above the eyes, on a narrow
	 * lens. The head's height is taken when the shot starts and its position follows the ground point, so a nod or a
	 * lowered head moves in the frame instead of the frame bobbing with it. Never closer than the model reaches, so the
	 * near plane does not cut into it.
	 */
	static final class Face implements CameraRig {
		final Follow follow;
		final Lens lens;
		final double distance, angle, height;
		final Reach reach;
		private double headHeight = Double.NaN, headAhead, nearest;

		Face(Params p, ShotContext shot) {
			follow = Follow.of(p, 0.3, 0.8, true);
			distance = range(p, "distance", 1.2, 0.3, 16);
			angle = range(p, "angle", 0, -170, 170);
			height = range(p, "height", 0, -2, 2);
			lens = new Lens(p, 30, shot);
			reach = new Reach(0.6);
		}

		@Override public View view() { return View.CAMERA; }
		@Override public int fov() { return lens.start(); }
		@Override public double fov(ShotContext shot) { return lens.fov(shot); }
		@Override public String subject() { return follow.subject; }

		@Override
		public Pose pose(ShotContext shot, float partialTick) {
			follow.update(shot);
			if (Double.isNaN(headHeight)) {
				Actor who = shot.actor(follow.subject);
				Vec3 g = who.ground(), h = who.head();
				headHeight = h.y - g.y;
				headAhead = new Vec3(h.x - g.x, 0, h.z - g.z).dot(Follow.forward(who.heading()));
				// The model may reach past its eye point (a snout, a beak): keep the lens outside its box.
				double width = who.entity() == null ? 0.6 : who.entity().getBbWidth();
				nearest = Math.max(0, width / 2 - headAhead) + 0.55;
			}
			double axis = follow.heading();
			Vec3 head = follow.anchor().add(Follow.forward(axis).scale(headAhead)).add(0, headHeight, 0);
			double d = Math.max(distance, nearest);
			Vec3 want = head.add(Follow.forward(axis + angle).scale(d)).add(0, height, 0);
			Vec3 eye = reach.eye(Rigs.probe, head, want, follow.velocity(), shot);
			// The smoothed head trails a walking subject: never let the real one come nearer than the model reaches.
			Vec3 real = shot.actor(follow.subject).head(), off = eye.subtract(real);
			double gap = off.length();
			if (gap < nearest) eye = gap < 1e-6 ? want : real.add(off.scale(nearest / gap));
			return look(eye, head, lens, shot);
		}
	}
}
