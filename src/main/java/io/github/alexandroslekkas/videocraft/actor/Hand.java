package io.github.alexandroslekkas.videocraft.actor;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * The human input model (ported from T3 Craft's DemoHand, MIT, same owner): how a person's hand moves a
 * mouse and presses keys, so the first-person shots do not read as a script. No Minecraft classes, and every random
 * choice comes from a seeded generator, so a take is reproducible.
 * <ul>
 * <li>{@link Look}: the view. A turn is a fast, slightly inaccurate movement with a bell-shaped, skewed speed profile
 * whose length follows the size of the turn (Fitts' law), then one or two small corrections that start before the
 * first movement has ended. A turn too big for one sweep of the wrist is two swipes with the mouse lifted between
 * them. Yaw and pitch do not move in proportion, so paths curve. Between turns the view drifts a fraction of a
 * degree (smooth noise, not jitter) and never sits perfectly still. The same model, in pixels, moves the mouse
 * pointer on a screen.</li>
 * <li>{@link #keyTimes}: when each key of a typed line goes down.</li>
 * <li>{@link #wait}: a human latency (noticing, reading, dwelling) with spread, never a round number of ticks.</li>
 * </ul>
 */
public final class Hand {
	private Hand() {}

	/** A latency of about {@code mean} seconds: log-normal with the given spread (0.2 = one fifth), at least 60% of the mean. */
	public static double wait(Random random, double mean, double spread) {
		return Math.max(mean * 0.6, mean * Math.exp(random.nextGaussian() * spread - spread * spread / 2));
	}

	/** Position along a movement at {@code k} of its time: minimum jerk, skewed so the peak comes early and the tail is long. */
	public static double reach(double k, double skew) {
		if (k <= 0) return 0;
		if (k >= 1) return 1;
		k = Math.pow(k, skew);
		return k * k * k * (k * (k * 6 - 15) + 10);
	}

	public static double wrap(double degrees) {
		degrees %= 360;
		return degrees >= 180 ? degrees - 360 : degrees < -180 ? degrees + 360 : degrees;
	}

	/** One movement of the hand: a change of view over a short time. */
	private static final class Sub {
		double start, yawTime, pitchTime, yaw, pitch, yawSkew, pitchSkew, bowYaw, bowPitch;

		public double end() { return start + Math.max(yawTime, pitchTime); }

		public double yawAt(double now) {
			double k = (now - start) / Math.max(yawTime, pitchTime);
			return yaw * reach((now - start) / yawTime, yawSkew) + bowYaw * bump(k);
		}

		public double pitchAt(double now) {
			double k = (now - start) / Math.max(yawTime, pitchTime);
			return pitch * reach((now - start) / pitchTime, pitchSkew) + bowPitch * bump(k);
		}

		private static double bump(double k) {
			if (k <= 0 || k >= 1) return 0;
			double s = Math.sin(Math.PI * k);
			return s * s;
		}
	}

	/** The view of a person holding a mouse. Times are seconds; angles are Minecraft's (yaw grows clockwise, pitch grows downward). */
	public static final class Look {
		private final Random random;
		private final List<Sub> subs = new ArrayList<>();
		private double now, baseYaw, basePitch;
		// Where the hand means to end up, and the corrections it still owes.
		private double goalYaw, goalPitch, tolerance = 0.5;
		private int corrections;
		private double correctAt = Double.NaN;
		// Following a moving target: looked at again every so often, like a person does.
		private boolean following;
		private double followAt, followSlack = 2;
		private double targetYaw, targetPitch, targetYawSpeed, targetPitchSpeed;
		// Drift: twice-smoothed noise.
		private double driftYaw, driftPitch, noiseYaw, noisePitch, driftScale = 1;
		private double fidgetAt = Double.NaN, fidgetSize = 0.9;
		// A turn in two swipes: where the second one ends, and when everything planned is over.
		private boolean staged;
		private double finalYaw, finalPitch, lastEnd, busyUntil;

		public Look(long seed, double yaw, double pitch) {
			random = new Random(seed);
			baseYaw = goalYaw = yaw;
			basePitch = goalPitch = pitch;
			// The noise starts settled, not at zero, so the first frames already move.
			noiseYaw = random.nextGaussian() * 0.25;
			noisePitch = random.nextGaussian() * 0.15;
			driftYaw = noiseYaw;
			driftPitch = noisePitch;
		}

		/** How much the idle view wanders: 1 is a calm hand, 0 a view the game holds still (a screen is open). */
		public void drift(double scale) { driftScale = scale; }

		/** Glances of about {@code degrees} now and then while nothing else happens; 0 stops them. */
		public void fidget(double degrees) {
			fidgetSize = degrees;
			fidgetAt = degrees > 0 ? now + 0.25 + random.nextDouble() * 0.7 : Double.NaN;
		}

		/** Turn to look at a point that stays put; lands a little off and corrects until within {@code tolerance} degrees. */
		public void turnTo(double yaw, double pitch, double tolerance) {
			following = false;
			this.tolerance = tolerance;
			double fromYaw = plannedYaw(), fromPitch = plannedPitch(), toYaw = fromYaw + wrap(yaw - fromYaw), size = Math.hypot(toYaw - fromYaw, pitch - fromPitch);
			corrections = 2;
			staged = size > 110;
			if (staged) {
				// Too far for one sweep of the wrist: a first swipe most of the way, a little off in height, the mouse lifted, a second.
				double part = 0.56 + random.nextDouble() * 0.12;
				finalYaw = toYaw;
				finalPitch = pitch;
				goalYaw = fromYaw + (toYaw - fromYaw) * part;
				goalPitch = fromPitch + (pitch - fromPitch) * part + (random.nextBoolean() ? 1 : -1) * (2 + random.nextDouble() * 2);
				move(1);
				correctAt = lastEnd + 0.06 + random.nextDouble() * 0.06;
				busyUntil = correctAt + span(size * (1 - part));
			} else {
				goalYaw = toYaw;
				goalPitch = pitch;
				correctAt = move(1);
				busyUntil = lastEnd;
			}
		}

		/** How long a movement of {@code size} degrees takes (Fitts' law; big turns are flicked, so their slope is half). */
		private static double span(double size) {
			double slope = 0.098 - 0.049 * Math.max(0, Math.min(1, (size - 12) / 48));
			return 0.15 + slope * Math.log(1 + size / 2.2) / Math.log(2);
		}

		/** A glance of a few degrees from wherever the view is heading. */
		public void nudge(double yaw, double pitch) {
			goalYaw = plannedYaw() + yaw;
			goalPitch = plannedPitch() + pitch;
			corrections = 0;
			move(1);
		}

		/** Keep the view on a moving target ({@link #aim} says where it is); {@code slack} is the error, in degrees, a person tolerates before moving. */
		public void follow(double slack) {
			if (!following) followAt = now + 0.03 + random.nextDouble() * 0.06;
			following = true;
			staged = false;
			followSlack = slack;
			correctAt = Double.NaN;
		}

		/** Where the followed target is now and how fast it moves, degrees and degrees per second. */
		public void aim(double yaw, double pitch, double yawSpeed, double pitchSpeed) {
			targetYaw = yaw;
			targetPitch = pitch;
			targetYawSpeed = yawSpeed;
			targetPitchSpeed = pitchSpeed;
		}

		public void stop() { following = false; staged = false; correctAt = Double.NaN; }

		public boolean moving() { return !subs.isEmpty() || !Double.isNaN(correctAt); }

		/** When the movements now under way end, in this look's own time. */
		public double settles() {
			double end = Math.max(now, staged ? busyUntil : now);
			for (Sub s : subs) end = Math.max(end, s.end());
			return end;
		}

		public double time() { return now; }

		private double plannedYaw() {
			double yaw = baseYaw;
			for (Sub s : subs) yaw += s.yaw;
			return yaw;
		}

		private double plannedPitch() {
			double pitch = basePitch;
			for (Sub s : subs) pitch += s.pitch;
			return pitch;
		}

		/** Starts a movement from where the hand will be toward the goal, with a human's error; returns when to check it. */
		private double move(double gainBias) {
			double yaw = goalYaw - plannedYaw(), pitch = goalPitch - plannedPitch(), size = Math.hypot(yaw, pitch);
			if (size < 0.02) return Double.NaN;
			// Primary movements tend to fall a few percent short; now and then one overshoots.
			double gain = gainBias * (0.955 + random.nextGaussian() * 0.04), side = random.nextGaussian() * 0.028;
			if (size < 3) { gain = 0.97 + random.nextGaussian() * 0.06; side *= 0.5; }
			gain = Math.max(0.8, Math.min(1.12, gain));
			Sub s = new Sub();
			s.start = now;
			s.yaw = yaw * gain - pitch * side;
			s.pitch = pitch * gain + yaw * side;
			// Fitts' law: longer for a bigger turn, about 0.3 s for 5 degrees and 0.4 s for 90.
			double time = span(size) * (1 + random.nextGaussian() * 0.07);
			// The two axes are not in step, so the path through the air curves.
			// A flick is one sweep of the arm, so its two axes end nearly together.
			double lead = 1 + random.nextGaussian() * (size > 40 ? 0.04 : 0.11);
			s.yawTime = time * Math.max(0.75, Math.min(1.25, lead));
			s.pitchTime = time * Math.max(0.75, Math.min(1.25, 2 - lead)) * (size > 40 || Math.abs(pitch) > Math.abs(yaw) ? 1 : 0.9);
			// A flick peaks early and brakes long; a small movement is nearly symmetric.
			double skew = size > 40 ? 0.65 : 0.8;
			s.yawSkew = skew + random.nextDouble() * 0.1;
			s.pitchSkew = skew + random.nextDouble() * 0.1;
			// The path bows to one side, a few degrees at most however big the turn.
			double bow = Math.max(-3.5, Math.min(3.5, random.nextGaussian() * Math.min(0.035 * size, 1.8)));
			s.bowYaw = -pitch / size * bow;
			s.bowPitch = yaw / size * bow;
			subs.add(s);
			lastEnd = s.end();
			// The correction is under way before the first movement has quite ended: no dead stop between them.
			return s.end() - time * (0.1 + random.nextDouble() * 0.12);
		}

		/** Advances by {@code dt} seconds and returns {yaw, pitch}. */
		public double[] step(double dt) {
			now += dt;
			for (int i = subs.size() - 1; i >= 0; i--) {
				Sub s = subs.get(i);
				if (now >= s.end()) { baseYaw += s.yaw; basePitch += s.pitch; subs.remove(i); }
			}
			if (following && now >= followAt) {
				// Look where the target will be when the hand gets there.
				double ahead = 0.16;
				goalYaw = plannedYaw() + wrap(targetYaw + targetYawSpeed * ahead - plannedYaw());
				goalPitch = targetPitch + targetPitchSpeed * ahead;
				double error = Math.hypot(goalYaw - plannedYaw(), goalPitch - plannedPitch());
				if (error > followSlack * (0.6 + random.nextDouble() * 0.6)) move(1.02);
				followAt = now + 0.11 + random.nextDouble() * 0.17;
			} else if (!following && staged && now >= correctAt) {
				staged = false;
				goalYaw = finalYaw;
				goalPitch = finalPitch;
				correctAt = move(1);
			} else if (!following && !Double.isNaN(correctAt) && now >= correctAt) {
				double error = Math.hypot(goalYaw - plannedYaw(), goalPitch - plannedPitch());
				correctAt = corrections-- > 0 && error > tolerance ? move(1.03) : Double.NaN;
			}
			if (!Double.isNaN(fidgetAt) && now >= fidgetAt && subs.isEmpty() && !following && Double.isNaN(correctAt)) {
				nudge(random.nextGaussian() * fidgetSize, random.nextGaussian() * fidgetSize * 0.5);
				fidgetAt = now + 0.6 + random.nextDouble() * 1.1;
			}
			// Drift: white noise smoothed twice (about 0.9 s, then 0.22 s), so it wanders without trembling.
			double a = dt / 0.9, b = dt / 0.22;
			noiseYaw += -noiseYaw * a + random.nextGaussian() * 0.34 * Math.sqrt(2 * a);
			noisePitch += -noisePitch * a + random.nextGaussian() * 0.2 * Math.sqrt(2 * a);
			driftYaw += (noiseYaw - driftYaw) * b;
			driftPitch += (noisePitch - driftPitch) * b;
			double yaw = baseYaw + driftYaw * driftScale, pitch = basePitch + driftPitch * driftScale;
			for (Sub s : subs) { yaw += s.yawAt(now); pitch += s.pitchAt(now); }
			return new double[] {yaw, Math.max(-89, Math.min(89, pitch))};
		}
	}

	/** Letter pairs the hands roll through quickly. */
	private static final String QUICK = "th he in er an re on at en nd ti es or te of ed is it al ar st to nt ng se ha as ou io le ve co me de hi ri ro ic ne ea ra ce li ch ll be ma si om ur sh ip";

	/**
	 * When each key of {@code text} goes down, in seconds from the first: quicker inside common letter pairs, slower at
	 * the start of a word, with the odd longer gap. About six keys a second.
	 */
	public static double[] keyTimes(String text, Random random) {
		double[] times = new double[text.length()];
		double at = 0;
		for (int i = 1; i < text.length(); i++) {
			char before = Character.toLowerCase(text.charAt(i - 1)), key = Character.toLowerCase(text.charAt(i));
			double gap = 0.155 * Math.exp(random.nextGaussian() * 0.24);
			if (before == ' ') gap *= 1.45;
			else if (key == ' ') gap *= 0.92;
			else if (QUICK.contains("" + before + key)) gap *= 0.76;
			else if (before == key) gap *= 0.9;
			if (random.nextDouble() < 0.08) gap += 0.09 + random.nextDouble() * 0.12;
			at += Math.max(0.055, gap);
			times[i] = at;
		}
		return times;
	}
}
