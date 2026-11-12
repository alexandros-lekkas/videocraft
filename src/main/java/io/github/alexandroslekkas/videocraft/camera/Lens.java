package io.github.alexandroslekkas.videocraft.camera;

import com.google.gson.JsonElement;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.ShotContext;

import java.util.Random;

/**
 * What every rig shares besides its path: the lens ({@code fov = 70}, or {@code fov = [from, to]} eased over the shot)
 * and an optional seeded handheld {@code drift}: a few tenths of a degree of slow wander in yaw and pitch, the same in
 * every take of the same plan.
 */
final class Lens {
	static final double MIN_FOV = 30, MAX_FOV = 110;

	final double from, to, drift;
	final String ease;
	private final double[] freq = new double[6], phase = new double[6];

	Lens(Params p, double fov, ShotContext shot) {
		JsonElement f = p.raw("fov");
		if (f != null && f.isJsonArray()) {
			if (f.getAsJsonArray().size() != 2) throw new IllegalArgumentException(p.where() + ": fov is a number or [from, to]");
			from = f.getAsJsonArray().get(0).getAsDouble();
			to = f.getAsJsonArray().get(1).getAsDouble();
		} else {
			from = to = p.number("fov", fov);
		}
		for (double v : new double[] {from, to})
			if (v < MIN_FOV || v > MAX_FOV) throw new IllegalArgumentException(p.where() + ": fov is " + MIN_FOV + " to " + MAX_FOV + " degrees, not " + v);
		ease = p.string("fov_ease", "smooth");
		Rigs.ease(ease, 0);
		drift = p.number("drift", 0);
		if (drift < 0 || drift > 3) throw new IllegalArgumentException(p.where() + ": drift is 0 to 3 degrees, not " + drift);
		// The drift's own generator: drawn once when the rig is made, so it does not disturb the shot's other draws.
		Random r = new Random(drift > 0 ? shot.random().nextLong() : 0);
		double[] base = {0.07, 0.13, 0.29};
		for (int i = 0; i < 6; i++) {
			freq[i] = base[i % 3] * (0.8 + 0.4 * r.nextDouble());
			phase[i] = r.nextDouble() * Math.PI * 2;
		}
	}

	/** The fov at shot time {@code t}. */
	double fov(ShotContext shot) {
		if (from == to) return from;
		double k = shot.duration() <= 0 ? 1 : shot.seconds() / shot.duration();
		return from + (to - from) * Rigs.ease(ease, k);
	}

	int start() { return (int) Math.round(from); }

	/** Degrees of handheld wander in yaw at time {@code t}. */
	double yaw(double t) { return wander(t, 0) * drift; }

	/** Degrees of handheld wander in pitch at time {@code t} (a little less than in yaw). */
	double pitch(double t) { return wander(t, 3) * drift * 0.6; }

	private double wander(double t, int at) {
		// Three slow sines of uneven periods (about 3 to 14 s), normalised to about one unit at most.
		double sum = 0;
		for (int i = at; i < at + 3; i++) sum += Math.sin(2 * Math.PI * freq[i] * t + phase[i]) / (1 + (i - at) * 0.6);
		return sum / 1.6;
	}
}
