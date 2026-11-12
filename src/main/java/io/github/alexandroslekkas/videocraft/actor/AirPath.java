package io.github.alexandroslekkas.videocraft.actor;

import java.util.ArrayList;
import java.util.List;

/**
 * A flight's line through the air: a smooth curve through the script's points in three dimensions (centripetal
 * Catmull-Rom, which never loops or overshoots a sharp corner), sampled densely and measured, so a flyer moves along it
 * by distance. The 3-D twin of {@link Path}; no Minecraft classes.
 */
public final class AirPath {
	private static final double STEP = 0.08;
	private final double[] xs, ys, zs, at;

	private AirPath(double[] xs, double[] ys, double[] zs, double[] at) {
		this.xs = xs;
		this.ys = ys;
		this.zs = zs;
		this.at = at;
	}

	/** A path through {@code points} ({x, y, z}) in order; two equal neighbours are one point. */
	public static AirPath through(List<double[]> points) {
		List<double[]> p = new ArrayList<>();
		for (double[] q : points) if (p.isEmpty() || dist(q, p.getLast()) > 1e-4) p.add(q);
		List<double[]> out = new ArrayList<>();
		out.add(p.getFirst());
		for (int i = 0; i + 1 < p.size(); i++) {
			double[] p1 = p.get(i), p2 = p.get(i + 1);
			// The ends continue straight on, so the curve leaves the first point and reaches the last one head-on.
			double[] p0 = i > 0 ? p.get(i - 1) : extend(p1, p2);
			double[] p3 = i + 2 < p.size() ? p.get(i + 2) : extend(p2, p1);
			int n = Math.max(2, (int) Math.ceil(dist(p1, p2) / STEP));
			for (int k = 1; k <= n; k++) out.add(catmull(p0, p1, p2, p3, k / (double) n));
		}
		int n = out.size();
		double[] xs = new double[n], ys = new double[n], zs = new double[n], at = new double[n];
		for (int i = 0; i < n; i++) {
			xs[i] = out.get(i)[0];
			ys[i] = out.get(i)[1];
			zs[i] = out.get(i)[2];
			if (i > 0) at[i] = at[i - 1] + dist(out.get(i), out.get(i - 1));
		}
		return new AirPath(xs, ys, zs, at);
	}

	private static double[] extend(double[] from, double[] away) {
		return new double[] {2 * from[0] - away[0], 2 * from[1] - away[1], 2 * from[2] - away[2]};
	}

	static double dist(double[] a, double[] b) {
		double dx = b[0] - a[0], dy = b[1] - a[1], dz = b[2] - a[2];
		return Math.sqrt(dx * dx + dy * dy + dz * dz);
	}

	private static double[] catmull(double[] p0, double[] p1, double[] p2, double[] p3, double u) {
		double t0 = 0, t1 = t0 + knot(p0, p1), t2 = t1 + knot(p1, p2), t3 = t2 + knot(p2, p3);
		double t = t1 + (t2 - t1) * u;
		double[] a1 = mix(p0, p1, t0, t1, t), a2 = mix(p1, p2, t1, t2, t), a3 = mix(p2, p3, t2, t3, t);
		double[] b1 = mix(a1, a2, t0, t2, t), b2 = mix(a2, a3, t1, t3, t);
		return mix(b1, b2, t1, t2, t);
	}

	private static double knot(double[] a, double[] b) { return Math.max(1e-4, Math.sqrt(dist(a, b))); }

	private static double[] mix(double[] a, double[] b, double ta, double tb, double t) {
		double w = (t - ta) / (tb - ta);
		return new double[] {a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w, a[2] + (b[2] - a[2]) * w};
	}

	public double length() { return at[at.length - 1]; }

	/** {x, y, z} at {@code s} blocks along (clamped to the ends). */
	public double[] at(double s) {
		int n = at.length - 1;
		if (s <= 0) return new double[] {xs[0], ys[0], zs[0]};
		if (s >= at[n]) return new double[] {xs[n], ys[n], zs[n]};
		int lo = 0, hi = n;
		while (hi - lo > 1) {
			int mid = (lo + hi) >>> 1;
			if (at[mid] <= s) lo = mid; else hi = mid;
		}
		double w = (s - at[lo]) / Math.max(1e-9, at[hi] - at[lo]);
		return new double[] {xs[lo] + (xs[hi] - xs[lo]) * w, ys[lo] + (ys[hi] - ys[lo]) * w, zs[lo] + (zs[hi] - zs[lo]) * w};
	}
}
