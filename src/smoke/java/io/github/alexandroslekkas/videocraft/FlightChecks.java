package io.github.alexandroslekkas.videocraft;

import io.github.alexandroslekkas.videocraft.actor.AirPath;
import io.github.alexandroslekkas.videocraft.actor.Flight;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Flying puppets without Minecraft ({@code actor.Flight}): a flight arrives on its point eased in and out with no
 * lurch, never falls, banks the right way into a turn, hands over between motions without a jump, a swarm keeps clear
 * of the body it circles and its members clear of each other, a landing ends on its (moving) spot and rides along, and
 * the same seed gives the same flight.
 */
public final class FlightChecks {
	static final double DT = 0.05;

	public static void main(String[] args) {
		airPath();
		route();
		hover();
		bankSign();
		handover();
		swarm();
		land();
		determinism();
		System.out.println("FlightChecks PASS");
	}

	static void airPath() {
		AirPath p = AirPath.through(List.of(new double[] {0, 64, 0}, new double[] {3, 68, 4}));
		double[] end = p.at(p.length());
		PlanChecks.check(Math.abs(p.length() - Math.sqrt(9 + 16 + 16)) < 1e-6, "a straight air path is its chord: " + p.length());
		PlanChecks.check(Math.abs(end[1] - 68) < 1e-9 && Math.abs(end[2] - 4) < 1e-9, "an air path ends on its last point");
	}

	/** Flies a path and returns the tick-by-tick speeds; checks arrival and smoothness. */
	static void route() {
		Flight f = new Flight(0, 70, 0, 0.7, new Random(1));
		f.place(new double[] {0, 70, 0}, new Random(2));
		f.fly(List.of(new double[] {4, 72, 6}, new double[] {10, 71, 4}), 2.6, 0.45, 0.6, 1, new Random(3));
		double last = 0, lastChange = 0, maxAccel = 0, maxJerk = 0, peak = 0;
		int ticks = 0;
		while (!f.arrived() && ticks < 400) {
			f.step(DT);
			double[] v = f.velocity();
			double sp = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]), change = sp - last;
			maxAccel = Math.max(maxAccel, Math.abs(change) / DT);
			if (ticks > 0) maxJerk = Math.max(maxJerk, Math.abs(change - lastChange));
			peak = Math.max(peak, sp);
			last = sp;
			lastChange = change;
			ticks++;
		}
		PlanChecks.check(f.arrived(), "a flight arrives");
		PlanChecks.check(Math.abs(f.x() - 10) < 0.25 && Math.abs(f.y() - 71) < 0.25 && Math.abs(f.z() - 4) < 0.25,
			"a flight ends at its last point: " + f.x() + " " + f.y() + " " + f.z());
		PlanChecks.check(peak > 2.2 && peak < 3.1, "a flight reaches its cruise: " + peak);
		// A bee darts off (up to 10 blocks/s/s) but its speed curve is smooth: no lurch at the start, the end or the bend.
		PlanChecks.check(maxAccel < 10, "a flight eases in and out: " + maxAccel + " blocks/s/s");
		PlanChecks.check(maxJerk < 0.15, "no lurch along a flight: " + maxJerk + " blocks/s per tick per tick");
		// Once arrived it hovers, slowing to the hover's drift.
		for (int i = 0; i < 60; i++) f.step(DT);
		double[] v = f.velocity();
		PlanChecks.check(Math.hypot(v[0], v[2]) < 0.6, "an arrived flyer hovers: " + Math.hypot(v[0], v[2]));
	}

	static void hover() {
		Flight f = new Flight(5, 80, 5, 0.7, new Random(8));
		f.place(new double[] {5, 80, 5}, new Random(9));
		f.hover(new double[] {5, 80, 5}, 0.3, 0.08, Double.NaN, new Random(10));
		double lo = 1e9, hi = -1e9, far = 0, maxStep = 0, py = f.y();
		for (int i = 0; i < 20 * 60; i++) {
			f.step(DT);
			lo = Math.min(lo, f.y());
			hi = Math.max(hi, f.y());
			far = Math.max(far, Math.hypot(f.x() - 5, f.z() - 5));
			maxStep = Math.max(maxStep, Math.abs(f.y() - py));
			py = f.y();
		}
		PlanChecks.check(lo > 79.8 && hi < 80.2, "a hover never falls or climbs away: " + lo + " to " + hi);
		PlanChecks.check(hi - lo > 0.05, "a hover bobs: " + (hi - lo));
		PlanChecks.check(far <= 0.31 && far > 0.05, "a hover drifts within its radius: " + far);
		PlanChecks.check(maxStep < 0.03, "a hover's bob is gentle: " + maxStep + " blocks per tick");
		PlanChecks.check(Math.abs(f.groundY() - 80) < 0.08, "the cameras' height ignores the bob: " + f.groundY());
	}

	/** Turning right (yaw increasing: south toward west) banks right wing down, which is positive. */
	static void bankSign() {
		Flight f = new Flight(0, 70, 0, 0.7, new Random(1));
		f.place(new double[] {0, 70, 0}, new Random(1));
		// Start south (+z), curve round to the west (-x): yaw goes 0 -> 90, a right turn.
		f.fly(List.of(new double[] {0, 70, 4}, new double[] {-2, 70, 7}, new double[] {-6, 70, 8}), 3, 0.3, 0.6, 1, new Random(2));
		double most = 0;
		for (int i = 0; i < 80 && !f.arrived(); i++) {
			f.step(DT);
			most = Math.max(most, f.bank());
			PlanChecks.check(Math.abs(f.bank()) <= 40.001, "bank stays within 40 degrees");
		}
		PlanChecks.check(most > 4, "a right turn banks right wing down (positive): " + most);
		Flight g = new Flight(0, 70, 0, 0.7, new Random(1));
		g.place(new double[] {0, 70, 0}, new Random(1));
		g.fly(List.of(new double[] {0, 74, 6}), 3, 0.3, 0.6, 1, new Random(2));
		double up = 0;
		for (int i = 0; i < 30; i++) { g.step(DT); up = Math.max(up, g.pitch()); }
		PlanChecks.check(up > 5, "a climb pitches the nose up: " + up);
	}

	/** Hover, then fly, then swarm, then hover: position and velocity carry across every change. */
	static void handover() {
		Flight f = new Flight(0, 70, 0, 0.7, new Random(5));
		f.hover(new double[] {0, 70, 0}, 0.3, 0.08, Double.NaN, new Random(6));
		double[] last = {f.x(), f.y(), f.z()};
		double[] lastV = f.velocity();
		double worstStep = 0, worstDv = 0;
		Flight.Anchor still = anchor(new double[] {3, 69, 3}, 0);
		for (int i = 0; i < 20 * 12; i++) {
			if (i == 40) f.fly(List.of(new double[] {4, 71, 2}), 2.6, 0.45, 0.6, 1, new Random(7));
			if (i == 90) f.orbit(still, null, f.lanes(1, 0.6, 0, 0)[0], 1.0, 2.4, 0.6, new Random(8));
			if (i == 170) f.hover(new double[] {6, 71, 6}, 0.2, 0.05, Double.NaN, new Random(9));
			f.step(DT);
			double[] v = f.velocity();
			double step = Math.sqrt(sq(f.x() - last[0]) + sq(f.y() - last[1]) + sq(f.z() - last[2]));
			double dv = Math.sqrt(sq(v[0] - lastV[0]) + sq(v[1] - lastV[1]) + sq(v[2] - lastV[2]));
			worstStep = Math.max(worstStep, step);
			worstDv = Math.max(worstDv, dv);
			last = new double[] {f.x(), f.y(), f.z()};
			lastV = v;
		}
		PlanChecks.check(worstStep < 0.3, "no jump between ticks across changes of motion: " + worstStep);
		PlanChecks.check(worstDv < 1.2, "no jolt in velocity across changes of motion: " + worstDv + " blocks/s per tick");
	}

	/** A body to circle: feet at {@code at} (moving east at {@code speed}), 0.6 wide, 1.8 tall, facing south. */
	static Flight.Anchor anchor(double[] at, double speed) {
		return new Flight.Anchor() {
			double t;

			@Override public double[] feet() { return new double[] {at[0] + speed * t, at[1], at[2]}; }

			@Override public double yaw() { return 0; }

			@Override public double width() { return 0.6; }

			@Override public double height() { return 1.8; }

			@Override public String toString() { return "anchor"; }

			void tick() { t += DT; }
		};
	}

	static void swarm() {
		for (long seed = 1; seed <= 24; seed++) {
			double speed = seed % 3 == 0 ? 0.8 : 0;
			double[] t = {0};
			double[] base = {0, 64, 0};
			Flight.Anchor body = new Flight.Anchor() {
				@Override public double[] feet() { return new double[] {base[0] + speed * t[0], base[1], base[2]}; }

				@Override public double yaw() { return 0; }

				@Override public double width() { return 0.6; }

				@Override public double height() { return 1.8; }
			};
			Random r = new Random(seed);
			int n = 3 + (int) (seed % 4);
			List<Flight> bees = new ArrayList<>();
			for (int i = 0; i < n; i++) {
				// They start scattered round the body, some on the far side of it, and fly in.
				double a = r.nextDouble() * 6.283, d = 2 + r.nextDouble() * 4;
				Flight f = new Flight(Math.cos(a) * d, 64.5 + r.nextDouble() * 2, Math.sin(a) * d, 0.7, new Random(r.nextLong()));
				bees.add(f);
			}
			double[] lanes = bees.getFirst().lanes(n, 0.6, 0, 0);
			for (int i = 0; i < n; i++) bees.get(i).orbit(body, null, lanes[i], 1.8 * 0.55, 2.4, lanes.length > 1 ? lanes[1] - lanes[0] : 0.6, new Random(seed * 31 + i));
			double clear = bees.getFirst().clearance(0.6);
			double nearestBody = 1e9, nearestPair = 1e9, lowest = 1e9;
			for (int tick = 0; tick < 20 * 30; tick++) {
				t[0] += DT;
				for (Flight f : bees) f.step(DT);
				double[] feet = body.feet();
				for (int i = 0; i < n; i++) {
					Flight f = bees.get(i);
					// Inside the body's height band, the horizontal distance to its axis is at least the clearance.
					if (f.y() > feet[1] - 0.4 && f.y() < feet[1] + 1.8 + 0.4)
						nearestBody = Math.min(nearestBody, Math.hypot(f.x() - feet[0], f.z() - feet[2]));
					if (tick > 60) lowest = Math.min(lowest, f.y() - feet[1]);
					if (tick > 60) for (int j = i + 1; j < n; j++) {
						Flight g = bees.get(j);
						nearestPair = Math.min(nearestPair, Math.sqrt(sq(f.x() - g.x()) + sq(f.y() - g.y()) + sq(f.z() - g.z())));
					}
				}
			}
			PlanChecks.check(nearestBody >= clear - 1e-6, "seed " + seed + ": a swarm never enters the body it circles: " + nearestBody + " < " + clear);
			PlanChecks.check(nearestPair > 0.42, "seed " + seed + ": two bees of a swarm never touch: " + nearestPair);
			PlanChecks.check(lowest > 0.2, "seed " + seed + ": a swarm stays above the floor: " + lowest);
		}
	}

	static void land() {
		double[] t = {0};
		Flight.Anchor walker = new Flight.Anchor() {
			@Override public double[] feet() { return new double[] {1.2 * t[0], 64, 0}; }

			@Override public double yaw() { return -90; }

			@Override public double width() { return 0.6; }

			@Override public double height() { return 1.8; }
		};
		Flight f = new Flight(-3, 67, 2, 0.35, new Random(4));
		double[] shoulder = {0, 0.34, 1.41};
		f.land(walker, shoulder, null, 2.2, new Random(5));
		int ticks = 0;
		while (f.airborne() && ticks < 400) { t[0] += DT; f.step(DT); ticks++; }
		PlanChecks.check(!f.airborne(), "a landing touches down");
		for (int i = 0; i < 40; i++) { t[0] += DT; f.step(DT); }
		// Facing east (yaw -90), the right shoulder is to the south (+z).
		double[] feet = walker.feet();
		PlanChecks.check(Math.abs(f.x() - feet[0]) < 0.02 && Math.abs(f.z() - 0.34) < 0.02 && Math.abs(f.y() - 65.41) < 0.02,
			"a landed flyer rides on its spot on a walking actor: " + (f.x() - feet[0]) + " " + f.z() + " " + f.y());
		Flight b = new Flight(0, 70, 0, 0.7, new Random(4));
		b.land(null, null, new double[] {3, 64, 2}, 2.2, new Random(5));
		ticks = 0;
		double low = 1e9;
		while (b.airborne() && ticks < 400) { b.step(DT); low = Math.min(low, b.y()); ticks++; }
		PlanChecks.check(!b.airborne() && Math.abs(b.y() - 64) < 0.01 && low > 63.99, "a landing on a block ends on its top without dipping under it: " + b.y() + " low " + low);
	}

	static void determinism() {
		double[] a = run(11), b = run(11), c = run(12);
		PlanChecks.check(java.util.Arrays.equals(a, b), "the same seed gives the same flight");
		PlanChecks.check(!java.util.Arrays.equals(a, c), "another seed gives another flight");
	}

	static double[] run(long seed) {
		Flight f = new Flight(0, 70, 0, 0.7, new Random(seed));
		f.fly(List.of(new double[] {5, 72, 5}), 2.6, 0.45, 0.6, 1, new Random(seed + 1));
		double[] out = new double[300];
		for (int i = 0; i < 100; i++) {
			f.step(DT);
			out[i * 3] = f.x();
			out[i * 3 + 1] = f.y();
			out[i * 3 + 2] = f.z();
		}
		return out;
	}

	static double sq(double v) { return v * v; }
}
