package io.github.alexandroslekkas.videocraft.actor;

import java.util.ArrayList;
import java.util.List;

/**
 * A walk's line on the ground plane: a smooth curve through the script's points (centripetal Catmull-Rom, which never
 * loops or overshoots a sharp corner), sampled densely and measured, so a walker moves along it by distance. No
 * Minecraft classes; angles are Minecraft yaw degrees (0 faces south, +z; 90 faces west, -x).
 */
public final class Path {
	private static final double STEP = 0.08;
	private final double[] xs, zs, at;

	private Path(double[] xs, double[] zs, double[] at) {
		this.xs = xs;
		this.zs = zs;
		this.at = at;
	}

	/** A path through {@code points} ({x, z} pairs) in order; two equal neighbours are one point. */
	public static Path through(List<double[]> points) {
		List<double[]> p = new ArrayList<>();
		for (double[] q : points) if (p.isEmpty() || Math.hypot(q[0] - p.getLast()[0], q[1] - p.getLast()[1]) > 1e-4) p.add(q);
		List<double[]> out = new ArrayList<>();
		out.add(p.getFirst());
		for (int i = 0; i + 1 < p.size(); i++) {
			double[] p1 = p.get(i), p2 = p.get(i + 1);
			// The ends continue in a straight line, so the curve leaves the first point and reaches the last one head-on.
			double[] p0 = i > 0 ? p.get(i - 1) : new double[] {2 * p1[0] - p2[0], 2 * p1[1] - p2[1]};
			double[] p3 = i + 2 < p.size() ? p.get(i + 2) : new double[] {2 * p2[0] - p1[0], 2 * p2[1] - p1[1]};
			int n = Math.max(2, (int) Math.ceil(Math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / STEP));
			for (int k = 1; k <= n; k++) out.add(catmull(p0, p1, p2, p3, k / (double) n));
		}
		double[] xs = new double[out.size()], zs = new double[out.size()], at = new double[out.size()];
		for (int i = 0; i < out.size(); i++) {
			xs[i] = out.get(i)[0];
			zs[i] = out.get(i)[1];
			if (i > 0) at[i] = at[i - 1] + Math.hypot(xs[i] - xs[i - 1], zs[i] - zs[i - 1]);
		}
		return new Path(xs, zs, at);
	}

	/** Centripetal Catmull-Rom (alpha 0.5) between p1 and p2 at {@code u} in 0..1. */
	private static double[] catmull(double[] p0, double[] p1, double[] p2, double[] p3, double u) {
		double t0 = 0, t1 = t0 + knot(p0, p1), t2 = t1 + knot(p1, p2), t3 = t2 + knot(p2, p3);
		double t = t1 + (t2 - t1) * u;
		double[] a1 = mix(p0, p1, t0, t1, t), a2 = mix(p1, p2, t1, t2, t), a3 = mix(p2, p3, t2, t3, t);
		double[] b1 = mix(a1, a2, t0, t2, t), b2 = mix(a2, a3, t1, t3, t);
		return mix(b1, b2, t1, t2, t);
	}

	private static double knot(double[] a, double[] b) { return Math.max(1e-4, Math.sqrt(Math.hypot(b[0] - a[0], b[1] - a[1]))); }

	private static double[] mix(double[] a, double[] b, double ta, double tb, double t) {
		double w = (t - ta) / (tb - ta);
		return new double[] {a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w};
	}

	public double length() { return at[at.length - 1]; }

	/** {x, z} at {@code s} blocks along (clamped to the ends). */
	public double[] at(double s) {
		if (s <= 0) return new double[] {xs[0], zs[0]};
		int n = at.length - 1;
		if (s >= at[n]) return new double[] {xs[n], zs[n]};
		int lo = 0, hi = n;
		while (hi - lo > 1) {
			int mid = (lo + hi) >>> 1;
			if (at[mid] <= s) lo = mid; else hi = mid;
		}
		double w = (s - at[lo]) / Math.max(1e-9, at[hi] - at[lo]);
		return new double[] {xs[lo] + (xs[hi] - xs[lo]) * w, zs[lo] + (zs[hi] - zs[lo]) * w};
	}

	/** The direction of travel around {@code s}, Minecraft yaw degrees (looked at over a short chord, so it never flickers). */
	public double heading(double s) {
		double a = Math.max(0, Math.min(length() - 0.05, s - 0.15)), b = Math.min(length(), Math.max(a + 0.05, s + 0.15));
		double[] p = at(a), q = at(b);
		return yaw(q[0] - p[0], q[1] - p[1]);
	}

	/** Minecraft yaw of a direction on the ground plane. */
	public static double yaw(double dx, double dz) { return Math.toDegrees(Math.atan2(dz, dx)) - 90; }

	/** Shortest signed difference of two angles in degrees, -180..180. */
	public static double wrap(double degrees) {
		degrees %= 360;
		return degrees >= 180 ? degrees - 360 : degrees < -180 ? degrees + 360 : degrees;
	}
}
