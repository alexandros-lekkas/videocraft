package io.github.alexandroslekkas.videocraft.actor;

/**
 * Where a puppet's feet are in height, tick by tick, given the ground under it: it steps up a slab or a stair over a
 * couple of ticks, hops a full block in a short arc, steps down small drops and falls off larger ones. Separately it
 * keeps a slow {@link #ground() ground reference} that ignores steps and hops, which is what cameras follow, so they do
 * not bob. Pure arithmetic.
 */
public final class Footing {
	/** Higher than this is hopped, not stepped. */
	static final double STEP = 0.6;
	/** Further than this in one tick, up or down, outside a recorded fall: a placement, not a movement. */
	static final double PLACE = 1.3;
	private double y, vy, ground;
	private boolean air;
	// A hop in progress: from where, to where above the ground, for how long.
	private double hopT = -1, hopTime, hopFrom, hopApex;
	private boolean placed;

	/** Puts the feet on {@code ground} at once (a placement). */
	public void place(double ground) {
		if (Double.isNaN(ground)) ground = placed ? y : 0;
		y = this.ground = ground;
		vy = 0;
		air = false;
		hopT = -1;
		placed = true;
	}

	/** A hop of {@code height} blocks above the ground, lasting {@code seconds}. */
	public void hop(double height, double seconds) {
		hopT = 0;
		hopTime = Math.max(0.15, seconds);
		hopFrom = y;
		hopApex = Math.max(0.05, height);
		air = true;
	}

	/**
	 * One tick of {@code dt} seconds over ground at height {@code target} ({@code NaN}: no ground found, stay level).
	 * {@code falls}: drops further than {@link #PLACE} are fallen (recording) rather than placed.
	 */
	public void step(double target, double dt, boolean falls) {
		if (!placed) { place(Double.isNaN(target) ? y : target); return; }
		if (Double.isNaN(target)) target = y;
		if (hopT >= 0) {
			hopT += dt;
			double k = Math.min(1, hopT / hopTime);
			// A parabola from where it left to the ground it lands on, peaking a little after halfway for a heavy body.
			double land = target, top = Math.max(hopFrom, land) + hopApex;
			double rise = Math.sin(Math.PI * Math.pow(k, 0.85));
			double base = hopFrom + (land - hopFrom) * Stride.smooth(k);
			y = base + (top - Math.max(hopFrom, land)) * rise;
			if (k >= 1) { y = land; hopT = -1; air = false; vy = 0; }
		} else if (target > y + 1e-3) {
			double rise = target - y;
			if (rise > PLACE) place(target);
			else if (rise > STEP) hop(0.28, 0.24 + 0.1 * rise);
			// A stair or a slab: up over about three ticks, the way a foot goes up a step.
			else y += Math.max(Math.min(rise, 0.06), rise * 0.5);
		} else if (target < y - 1e-3 || air) {
			double drop = y - target;
			if (!air && drop <= STEP) {
				y -= Math.max(Math.min(drop, 0.06), drop * 0.5);
			} else if (!falls && drop > PLACE) {
				place(target);
			} else {
				air = true;
				vy -= 28 * dt;
				y += vy * dt;
				if (y <= target) { y = target; vy = 0; air = false; }
			}
		}
		// The camera's ground: smoothed over about a quarter of a second, never part of a hop or a stride.
		double settled = hopT >= 0 ? Math.min(y, Math.max(hopFrom, target)) : air ? ground : y;
		ground += (settled - ground) * (1 - Math.exp(-dt / 0.22));
		if (Math.abs(settled - ground) > PLACE * 2) ground = settled;
	}

	public double y() { return y; }

	public double ground() { return ground; }

	/** In a hop or a fall. */
	public boolean air() { return air; }
}
