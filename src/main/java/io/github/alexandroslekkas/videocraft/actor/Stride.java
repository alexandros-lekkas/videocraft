package io.github.alexandroslekkas.videocraft.actor;

import java.util.Random;

/**
 * How fast a walker moves along its {@link Path}: it eases up to its pace over {@code accel} seconds (from whatever
 * speed it already had, so walks chain without a stop), holds a pace that breathes a few percent with each stride, and
 * brakes over about {@code arrive} seconds so it lands on the last point without a lurch. Pure arithmetic per game
 * tick; the seed makes each walk a little different (pace, ramp) but the same take every time.
 */
public final class Stride {
	/** Seconds a walk carried over a cut takes to stop when the new shot gives its walker another movement cue. */
	public static final double CUT_STOP = 0.25;

	private final Path path;
	private final double cruise, accel, arrive, from, wobble, phase;
	private double s, v, t;
	private boolean done, stopping;

	public Stride(Path path, double speed, double accel, double arrive, double startSpeed, Random random) {
		this.path = path;
		// A person never walks at exactly the same pace twice.
		this.cruise = speed * (1 + random.nextGaussian() * 0.025);
		this.accel = Math.max(0.05, accel * (0.9 + random.nextDouble() * 0.2));
		this.arrive = Math.max(0, arrive * (0.9 + random.nextDouble() * 0.2));
		this.from = Math.max(0, Math.min(startSpeed, cruise));
		this.wobble = 0.025 + random.nextDouble() * 0.015;
		this.phase = random.nextDouble() * Math.PI * 2;
		this.v = from;
	}

	/** Brake now and stop within about {@code seconds} (the path is cut short where the walker comes to rest). */
	public void stop(double seconds) {
		if (done) return;
		stopping = true;
		double brake = Math.max(0.05, seconds);
		// Constant deceleration from the current speed covers v * t / 2.
		stopAt = Math.min(path.length(), s + v * brake / 2);
	}

	private double stopAt = Double.NaN;

	/** One step of {@code dt} seconds; returns the distance along the path. */
	public double step(double dt) {
		if (done) return s;
		t += dt;
		double end = stopping ? stopAt : path.length(), rem = end - s;
		double ramp = smooth(t / accel), want = from + (cruise - from) * ramp;
		want *= 1 + wobble * Math.sin(t * 2 * Math.PI * 0.9 + phase) * ramp;
		if (arrive > 0 || stopping) {
			// Constant braking from cruise to rest over `arrive` seconds, then a short exponential tail so it settles
			// on the point instead of stopping dead in the middle of a stride.
			double decel = cruise / Math.max(0.05, stopping && arrive == 0 ? 0.3 : arrive);
			double brake = Math.min(Math.sqrt(2 * decel * Math.max(0, rem)), rem / 0.09 + 0.03);
			want = Math.min(want, brake);
		}
		v = want;
		s += v * dt;
		if (s >= end - 0.004) {
			s = end;
			v = 0;
			done = true;
		}
		return s;
	}

	public boolean done() { return done; }

	public double speed() { return v; }

	public double distance() { return s; }

	public Path path() { return path; }

	static double smooth(double k) {
		k = Math.max(0, Math.min(1, k));
		return k * k * (3 - 2 * k);
	}
}
