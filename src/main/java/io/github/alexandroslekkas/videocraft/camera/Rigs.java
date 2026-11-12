package io.github.alexandroslekkas.videocraft.camera;

import io.github.alexandroslekkas.videocraft.api.CameraRig;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.Pose;
import io.github.alexandroslekkas.videocraft.api.Registry;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import io.github.alexandroslekkas.videocraft.api.View;
import net.minecraft.world.phys.Vec3;

/**
 * Built-in camera rigs. Owned by workstream (a). Each is a pure function of the shot clock and its parameters (plus,
 * for rigs that follow someone, where that actor is), so a take is reproducible. Rigs that film a subject follow its
 * ground reference through {@link Operator} ({@link Moves}). Reference: docs/SCRIPT.md, "Camera rigs".
 */
public final class Rigs {
	private Rigs() {}

	/** How rigs see blocks; RigChecks swaps in plain geometry. */
	public static Probe probe = Probe.LEVEL;

	public static void register(Registry r) {
		r.rig("orbit", Orbit::new);
		r.rig("fixed", Fixed::new);
		r.rig("lead", Moves.Lead::new);
		r.rig("chase", Moves.Chase::new);
		r.rig("track", Moves.Track::new);
		r.rig("dolly", Moves.Dolly::new);
		r.rig("crane", Moves::crane);
		r.rig("locked", Moves::locked);
		r.rig("two_shot", Moves.TwoShot::new);
		r.rig("face", Moves.Face::new);
		// The player's own eyes: no pose, the actor turns the view.
		r.rig("first", (p, shot) -> new CameraRig() {
			@Override public View view() { return View.FIRST; }
			@Override public Pose pose(ShotContext s, float partialTick) { return null; }
			@Override public int fov() { return (int) p.number("fov", 70); }
		});
	}

	/** {@code k} in 0..1 through an easing: linear, or smooth (ease in and out). */
	public static double ease(String kind, double k) {
		k = Math.max(0, Math.min(1, k));
		return switch (kind) {
			case "linear" -> k;
			case "smooth" -> k * k * (3 - 2 * k);
			case "out" -> 1 - (1 - k) * (1 - k);
			default -> throw new IllegalArgumentException("ease is linear, smooth or out, not " + kind);
		};
	}

	/**
	 * Circles {@code center} at {@code radius} blocks and {@code height} above it, from {@code from} degrees through
	 * {@code sweep} degrees over the shot, looking at {@code look} (default the center). 0 degrees is south of the
	 * center; positive sweeps go clockwise seen from above.
	 */
	static final class Orbit implements CameraRig {
		final Vec3 center, look;
		final double radius, height, from, sweep;
		final String ease;
		final Lens lens;

		Orbit(Params p, ShotContext shot) {
			center = shot.position(p, "center");
			look = p.has("look") ? shot.position(p, "look") : center;
			radius = p.number("radius", 8);
			height = p.number("height", 3);
			from = p.number("from", 0);
			sweep = p.number("sweep", 90);
			ease = p.string("ease", "linear");
			ease(ease, 0);
			lens = new Lens(p, 70, shot);
			if (radius <= 0) throw new IllegalArgumentException(p.where() + ": radius must be > 0");
		}

		@Override public View view() { return View.CAMERA; }
		@Override public int fov() { return lens.start(); }
		@Override public double fov(ShotContext shot) { return lens.fov(shot); }

		@Override
		public Pose pose(ShotContext shot, float partialTick) {
			double angle = Math.toRadians(from + sweep * ease(ease, Moves.progress(shot)));
			Vec3 eye = center.add(-Math.sin(angle) * radius, height, Math.cos(angle) * radius);
			return Moves.look(eye, look, lens, shot);
		}
	}

	/** A locked-off camera at {@code eye} looking at {@code at}. */
	static final class Fixed implements CameraRig {
		final Vec3 eye, at;
		final Lens lens;

		Fixed(Params p, ShotContext shot) {
			eye = shot.position(p, "eye");
			at = shot.position(p, "at");
			lens = new Lens(p, 70, shot);
		}

		@Override public View view() { return View.CAMERA; }
		@Override public int fov() { return lens.start(); }
		@Override public double fov(ShotContext shot) { return lens.fov(shot); }
		@Override public Pose pose(ShotContext shot, float partialTick) { return Moves.look(eye, at, lens, shot); }
	}
}
