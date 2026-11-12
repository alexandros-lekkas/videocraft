package io.github.alexandroslekkas.videocraft.actor;

import java.util.Random;

/**
 * Small idle life between scripted beats: now and then a glance (the head goes a few to twenty-odd degrees off and
 * comes back), and a slow weight shift of the body. A scripted beat (a walk's turn, a look, a turn, a gesture) holds it
 * off, and it waits a moment after one ends before glancing again, so it never fights the script. Pure; the seed sets
 * its rhythm. {@code busy} birds glance often and quickly; {@code calm} animals and people rarely and slowly.
 */
public final class Life {
	public enum Temper { OFF, CALM, BUSY }

	private final Random random;
	private final Temper temper;
	private double now, next, until, yaw, pitch, swayPeriod, swayPhase;

	public Life(Random random, Temper temper) {
		this.random = random;
		this.temper = temper;
		next = 0.6 + random.nextDouble() * 1.5;
		swayPeriod = 3.2 + random.nextDouble() * 2.4;
		swayPhase = random.nextDouble() * Math.PI * 2;
	}

	/** One tick; {@code free}: nothing scripted is using the head now. */
	public void step(double dt, boolean free, boolean walking) {
		now += dt;
		if (temper == Temper.OFF) return;
		if (!free) {
			yaw = pitch = 0;
			until = now;
			next = Math.max(next, now + (temper == Temper.BUSY ? 0.3 : 0.7) + random.nextDouble() * 0.6);
			return;
		}
		if (now >= until && (yaw != 0 || pitch != 0)) { yaw = 0; pitch = 0; }
		if (now >= next) {
			boolean busy = temper == Temper.BUSY;
			double size = busy ? 10 + random.nextDouble() * 30 : 7 + random.nextDouble() * 20;
			if (walking) size *= 0.45;
			yaw = (random.nextBoolean() ? 1 : -1) * size;
			pitch = (random.nextDouble() - 0.4) * (busy ? 26 : 12);
			until = now + (busy ? 0.25 + random.nextDouble() * 0.6 : 0.55 + random.nextDouble() * 1.1);
			// Sometimes a glance is answered by a second one the other way, the way a head checks both sides.
			next = until + (busy && random.nextDouble() < 0.4 ? 0.05 : (busy ? 0.4 : 1.3) + random.nextDouble() * (busy ? 1.2 : 2.6));
		}
	}

	public double yaw() { return yaw; }

	public double pitch() { return pitch; }

	/** The weight shift: a degree or two of body yaw, slow. */
	public double sway() { return temper == Temper.OFF ? 0 : 1.4 * Math.sin(now * 2 * Math.PI / swayPeriod + swayPhase); }
}
