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
 * for rigs that follow someone, where that actor is), so a take is reproducible. Planned (docs/DESIGN.md): first,
 * third (chase), track, dolly, crane, locked, two-shot; all following a ground reference through {@link Operator}.
 */
public final class Rigs {
	private Rigs() {}

	public static void register(Registry r) {
		r.rig("orbit", Orbit::new);
		r.rig("fixed", Fixed::new);
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
		final int fov;

		Orbit(Params p, ShotContext shot) {
			center = shot.position(p, "center");
			look = p.has("look") ? shot.position(p, "look") : center;
			radius = p.number("radius", 8);
			height = p.number("height", 3);
			from = p.number("from", 0);
			sweep = p.number("sweep", 90);
			ease = p.string("ease", "linear");
			fov = (int) p.number("fov", 70);
			if (radius <= 0) throw new IllegalArgumentException(p.where() + ": radius must be > 0");
		}

		@Override public View view() { return View.CAMERA; }
		@Override public int fov() { return fov; }

		@Override
		public Pose pose(ShotContext shot, float partialTick) {
			double k = shot.duration() <= 0 ? 0 : shot.seconds() / shot.duration();
			return at(Math.toRadians(from + sweep * ease(ease, k)));
		}

		Pose at(double angle) {
			Vec3 eye = center.add(-Math.sin(angle) * radius, height, Math.cos(angle) * radius);
			return Pose.looking(eye, look);
		}
	}

	/** A locked-off camera at {@code eye} looking at {@code at}. */
	static final class Fixed implements CameraRig {
		final Pose pose;
		final int fov;

		Fixed(Params p, ShotContext shot) {
			pose = Pose.looking(shot.position(p, "eye"), shot.position(p, "at"));
			fov = (int) p.number("fov", 70);
		}

		@Override public View view() { return View.CAMERA; }
		@Override public int fov() { return fov; }
		@Override public Pose pose(ShotContext shot, float partialTick) { return pose; }
	}
}
