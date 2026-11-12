package io.github.alexandroslekkas.videocraft.camera;

/**
 * A camera operator: follows a wanted value with a critically damped spring, so the camera lags behind action,
 * catches up and settles without overshoot. {@code lag} is roughly the seconds it trails by.
 */
public final class Operator {
	private final double[] at, speed;
	private boolean placed;

	public Operator(int size) {
		at = new double[size];
		speed = new double[size];
	}

	public void cut() { placed = false; }

	public double[] follow(double[] want, double lag, double dt) {
		if (!placed || lag <= 0) {
			System.arraycopy(want, 0, at, 0, at.length);
			java.util.Arrays.fill(speed, 0);
			placed = true;
			return at;
		}
		double omega = 2 / lag, decay = Math.exp(-omega * dt);
		for (int i = 0; i < at.length; i++) {
			double offset = at[i] - want[i], change = (speed[i] + omega * offset) * dt;
			speed[i] = (speed[i] - omega * change) * decay;
			at[i] = want[i] + (offset + change) * decay;
		}
		return at;
	}

	/** How fast the followed value is moving now, per second (smooth: the spring's own speed). */
	public double[] speed() { return speed.clone(); }

	/** Starts the spring already moving with its subject, so a shot that begins in motion does not begin by catching up. */
	public void carry(double[] velocity) { System.arraycopy(velocity, 0, speed, 0, speed.length); }
}
