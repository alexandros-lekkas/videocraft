package io.github.alexandroslekkas.videocraft;

import io.github.alexandroslekkas.videocraft.actor.Footing;
import io.github.alexandroslekkas.videocraft.actor.Heading;
import io.github.alexandroslekkas.videocraft.actor.Life;
import io.github.alexandroslekkas.videocraft.actor.Path;
import io.github.alexandroslekkas.videocraft.actor.Stride;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * The puppets' motion without Minecraft: a walk's curve and pace, the feet over steps, the head and body turning, idle
 * life. Bounds are what reads as alive on screen: no pops (jumps between ticks), no lurches (sudden changes of speed),
 * no overshooting turns, the head arriving before the body, and the same seed giving the same motion.
 */
public final class ActorChecks {
	static final double DT = 0.05;

	public static void main(String[] args) {
		path();
		stride();
		footing();
		heading();
		life();
		System.out.println("ActorChecks PASS");
	}

	static void path() {
		Path p = Path.through(List.of(new double[] {0, 0}, new double[] {2, 4}, new double[] {0, 8}));
		double[] end = p.at(p.length());
		PlanChecks.check(Math.abs(end[0]) < 1e-6 && Math.abs(end[1] - 8) < 1e-6, "path ends on its last point");
		PlanChecks.check(p.length() > 8.9 && p.length() < 10.5, "a bent path is longer than its chord: " + p.length());
		// The tangent turns smoothly: no corner sharper than a few degrees between samples 0.1 blocks apart.
		double worst = 0, last = p.heading(0);
		for (double s = 0.1; s < p.length(); s += 0.1) {
			double h = p.heading(s);
			worst = Math.max(worst, Math.abs(Path.wrap(h - last)));
			last = h;
		}
		PlanChecks.check(worst < 6, "the path's heading never kinks: " + worst + " degrees per 0.1 block");
		PlanChecks.check(Math.abs(Path.yaw(0, 1)) < 1e-9 && Math.abs(Path.yaw(-1, 0) - 90) < 1e-9, "yaw: south 0, west 90");
	}

	static void stride() {
		Path p = Path.through(List.of(new double[] {0, 0}, new double[] {0, 12}));
		Stride a = new Stride(p, 1.8, 0.35, 0.5, 0, new Random(4)), b = new Stride(p, 1.8, 0.35, 0.5, 0, new Random(4));
		List<Double> speeds = new ArrayList<>();
		int ticks = 0;
		while (!a.done() && ticks < 400) {
			double sa = a.step(DT), sb = b.step(DT);
			PlanChecks.check(sa == sb, "a walk is reproducible from its seed");
			speeds.add(a.speed());
			ticks++;
		}
		PlanChecks.check(a.done() && Math.abs(a.distance() - 12) < 1e-9, "the walk arrives on its point: " + a.distance());
		double peak = speeds.stream().mapToDouble(Double::doubleValue).max().orElse(0);
		PlanChecks.check(peak > 1.6 && peak < 2.0, "the walk reaches its pace: " + peak);
		PlanChecks.check(speeds.getFirst() < 0.4, "the walk eases in from rest: " + speeds.getFirst());
		// No lurch: the steepest change is the start (a 0.35 s ramp to pace), under a quarter of the pace per tick.
		double jerk = 0;
		for (int i = 1; i < speeds.size(); i++) jerk = Math.max(jerk, Math.abs(speeds.get(i) - speeds.get(i - 1)));
		PlanChecks.check(jerk < 0.45, "speed changes smoothly: " + jerk + " blocks/s per tick");
		// The last moving tick is slow: it settles, it does not slam into the mark.
		PlanChecks.check(speeds.get(speeds.size() - 2) < 0.6, "the walk eases out: " + speeds.get(speeds.size() - 2));
		// A different seed walks a little differently.
		Stride c = new Stride(p, 1.8, 0.35, 0.5, 0, new Random(5));
		for (int i = 0; i < 40; i++) c.step(DT);
		Stride d = new Stride(p, 1.8, 0.35, 0.5, 0, new Random(4));
		for (int i = 0; i < 40; i++) d.step(DT);
		PlanChecks.check(c.distance() != d.distance(), "seeds vary the pace");
	}

	static void footing() {
		// Up a slab, along, down again: smooth (no tick moves more than a step's share), and the camera's ground lags softly.
		Footing f = new Footing();
		f.place(100);
		double last = 100, worst = 0, groundWorst = 0, lastGround = 100;
		for (int i = 0; i < 60; i++) {
			double target = i >= 10 && i < 30 ? 100.5 : 100;
			f.step(target, DT, true);
			worst = Math.max(worst, Math.abs(f.y() - last));
			groundWorst = Math.max(groundWorst, Math.abs(f.ground() - lastGround));
			last = f.y();
			lastGround = f.ground();
		}
		PlanChecks.check(Math.abs(f.y() - 100) < 1e-3, "back down on the ground: " + f.y());
		PlanChecks.check(worst <= 0.26, "a slab is stepped over a few ticks, not popped: " + worst);
		PlanChecks.check(groundWorst < 0.12, "the camera's ground reference glides over steps: " + groundWorst);
		// A full block up is hopped: in the air for a moment, landing on top.
		Footing g = new Footing();
		g.place(100);
		boolean flew = false;
		for (int i = 0; i < 30; i++) {
			g.step(101, DT, true);
			flew |= g.air();
		}
		PlanChecks.check(flew && Math.abs(g.y() - 101) < 1e-6 && !g.air(), "a block is hopped and landed on: " + g.y());
		// A scripted hop goes up and comes back to the ground, and the camera's ground does not follow it up.
		Footing h = new Footing();
		h.place(100);
		h.hop(0.6, 0.4);
		double top = 0, groundTop = 0;
		for (int i = 0; i < 20; i++) {
			h.step(100, DT, true);
			top = Math.max(top, h.y());
			groundTop = Math.max(groundTop, h.ground());
		}
		PlanChecks.check(top > 100.5 && Math.abs(h.y() - 100) < 1e-6, "a hop rises and lands: top " + top);
		PlanChecks.check(groundTop < 100.01, "a hop does not lift the camera's ground: " + groundTop);
	}

	static void heading() {
		Heading h = new Heading(0, 50, new Random(3));
		h.turn(120, 1);
		double maxBody = 0, headFirst = 0;
		boolean headAhead = false;
		for (int i = 0; i < 60; i++) {
			h.step(DT, 0, 0, 0);
			maxBody = Math.max(maxBody, h.body());
			if (i == 4) headAhead = h.head() > h.body() + 5;
			headFirst = Math.max(headFirst, Math.abs(Path.wrap(h.head() - h.body())));
		}
		PlanChecks.check(Math.abs(h.body() - 120) < 0.5 && Math.abs(h.head() - 120) < 0.5, "the turn settles on its goal: " + h.body());
		PlanChecks.check(maxBody < 120.5, "the body does not overshoot: " + maxBody);
		PlanChecks.check(headAhead, "the head leads the turn");
		PlanChecks.check(headFirst <= 50 + 1e-6, "the head stays within the neck's reach: " + headFirst);
		// The shortest way round: from 170 to -170 is 20 degrees, not 340.
		Heading w = new Heading(170, 50, new Random(3));
		w.turn(-170, 1);
		for (int i = 0; i < 60; i++) w.step(DT, 0, 0, 0);
		PlanChecks.check(Math.abs(w.body() - 190) < 0.5, "turns take the short way: " + w.body());
	}

	static void life() {
		Life a = new Life(new Random(9), Life.Temper.CALM), b = new Life(new Random(9), Life.Temper.CALM);
		boolean glanced = false;
		for (int i = 0; i < 400; i++) {
			a.step(DT, true, false);
			b.step(DT, true, false);
			PlanChecks.check(a.yaw() == b.yaw() && a.pitch() == b.pitch(), "idle life is reproducible");
			glanced |= a.yaw() != 0;
		}
		PlanChecks.check(glanced, "an idle animal glances about");
		for (int i = 0; i < 40; i++) {
			a.step(DT, false, false);
			PlanChecks.check(a.yaw() == 0 && a.pitch() == 0, "idle life never fights a scripted beat");
		}
	}
}
