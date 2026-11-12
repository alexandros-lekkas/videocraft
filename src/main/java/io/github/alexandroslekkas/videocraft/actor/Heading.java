package io.github.alexandroslekkas.videocraft.actor;

import java.util.Random;

/**
 * Which way a puppet's body and head face, tick by tick. Each angle follows its goal on a critically damped spring,
 * whose speed profile (a fast start that peaks early, then a long settle) is the shape of a person's or an animal's
 * turn; the head is quicker than the body and starts first, so a turn is led by the eyes. The head stays within
 * {@code reach} degrees of the body. Pure arithmetic; Minecraft yaw degrees, pitch positive downward.
 */
public final class Heading {
	private final Random random;
	private double body, bodyV, head, headV, pitch, pitchV;
	private double bodyGoal, bodyOmega = 8, headOmega = 16, pitchOmega = 14;
	// The head's own goal: NaN follows the body (plus the offsets of idle life and gestures).
	private double lookYaw = Double.NaN, lookPitch;
	private double bodyWait;
	private double reach;

	public Heading(double yaw, double reach, Random random) {
		this.random = random;
		this.reach = reach;
		place(yaw);
	}

	/** Faces {@code yaw} at once, head forward. */
	public void place(double yaw) {
		body = head = bodyGoal = yaw;
		bodyV = headV = pitchV = 0;
		pitch = 0;
		lookYaw = Double.NaN;
	}

	/**
	 * Turn the whole animal to {@code yaw}: the head goes first, the body follows after a short human delay. {@code
	 * pace} scales the speed (1 a calm turn, 2 a snap).
	 */
	public void turn(double yaw, double pace) {
		bodyGoal = body + Path.wrap(yaw - body);
		double size = Math.abs(bodyGoal - body);
		// Bigger turns are a little slower, never a constant rate; each one differs a little.
		bodyOmega = pace * (9.5 - Math.min(3.5, size / 40)) * (0.88 + random.nextDouble() * 0.24);
		headOmega = pace * 17 * (0.9 + random.nextDouble() * 0.2);
		bodyWait = (0.06 + random.nextDouble() * 0.1) / pace;
	}

	/** While walking: the body follows the direction of travel without the delay of a turn in place. */
	public void travel(double yaw, double omega) {
		bodyGoal = body + Path.wrap(yaw - body);
		bodyOmega = omega;
		bodyWait = 0;
	}

	/** Point the head at a world yaw and pitch (clamped to the reach of the neck); NaN yaw: back to the body. */
	public void look(double yaw, double pitch) {
		lookYaw = yaw;
		lookPitch = pitch;
	}

	public void headSpeed(double omega) { headOmega = omega; }

	public void reach(double degrees) { reach = degrees; }

	public boolean looking() { return !Double.isNaN(lookYaw); }

	/** Whether the body is still turning toward its goal. */
	public boolean turning() { return Math.abs(bodyGoal - body) > 0.8 || Math.abs(bodyV) > 4; }

	/**
	 * One tick. {@code idleYaw}/{@code idlePitch} are idle life's head offsets from forward, {@code chin} the gait's
	 * carriage (negative: head held high).
	 */
	public void step(double dt, double idleYaw, double idlePitch, double chin) {
		if (bodyWait > 0) bodyWait -= dt;
		else {
			double[] b = spring(body, bodyV, bodyGoal, bodyOmega, dt);
			body = b[0];
			bodyV = b[1];
		}
		double wantYaw, wantPitch;
		if (Double.isNaN(lookYaw)) {
			// Forward is where the body is going, so on a turn the head arrives first.
			wantYaw = bodyGoal + idleYaw;
			wantPitch = chin + idlePitch;
		} else {
			wantYaw = lookYaw;
			wantPitch = lookPitch + chin * 0.3;
		}
		wantYaw = head + Path.wrap(wantYaw - head);
		double[] h = spring(head, headV, wantYaw, headOmega, dt);
		head = h[0];
		headV = h[1];
		double rel = Path.wrap(head - body);
		if (Math.abs(rel) > reach) { head = body + Math.copySign(reach, rel); headV = bodyV; }
		double[] p = spring(pitch, pitchV, Math.max(-60, Math.min(60, wantPitch)), pitchOmega, dt);
		pitch = p[0];
		pitchV = p[1];
	}

	/** The exact step of a critically damped spring: {value, velocity}. */
	static double[] spring(double x, double v, double goal, double omega, double dt) {
		double off = x - goal, decay = Math.exp(-omega * dt), change = (v + omega * off) * dt;
		return new double[] {goal + (off + change) * decay, (v - omega * change) * decay};
	}

	public double body() { return body; }

	public double head() { return head; }

	public double pitch() { return pitch; }

	public double bodyGoal() { return bodyGoal; }
}
