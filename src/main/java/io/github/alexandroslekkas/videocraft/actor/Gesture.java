package io.github.alexandroslekkas.videocraft.actor;

import java.util.Arrays;
import java.util.Locale;

/**
 * Body language as plain angles: head gestures any actor can make (a nod, a shake, the small nods of talking) and the
 * arm poses of a player-shaped actor (wave, point, shrug, cheer, facepalm, type, talk, think, hold), ported from T3
 * Craft's {@code AgentLife} (MIT, same owner). A gesture eases in over a few ticks, plays, and eases out; nothing snaps.
 * Times are seconds since the gesture began; arm channels are radians on top of (or instead of: NaN keeps vanilla)
 * the model's own pose. No Minecraft classes.
 */
public final class Gesture {
	/** Arm channels: right arm x/y/z, left arm x/y/z, extra head pitch and roll, in radians. */
	public static final int RAX = 0, RAY = 1, RAZ = 2, LAX = 3, LAY = 4, LAZ = 5, HEAD_X = 6, HEAD_Z = 7, CHANNELS = 8;

	public enum Kind {
		NOD, SHAKE, TALK, WAVE, POINT, SHRUG, CHEER, FACEPALM, TYPE, THINK, HOLD;

		static Kind of(String name, String where) {
			try {
				return valueOf(name.toUpperCase(Locale.ROOT));
			} catch (IllegalArgumentException e) {
				throw new IllegalArgumentException(where + ": no gesture '" + name + "'; known: " + Arrays.toString(values()).toLowerCase(Locale.ROOT));
			}
		}

		/** Gestures with arms need a player-shaped body. */
		boolean arms() { return this != NOD && this != SHAKE && this != TALK; }
	}

	final Kind kind;
	final double length, size;
	final int seed;
	final double start;
	double release = Double.NaN;

	/** {@code length}: seconds (infinite holds until released); {@code size}: a scale on the movement (1 normal). */
	Gesture(Kind kind, double start, double length, double size, int seed) {
		this.kind = kind;
		this.start = start;
		this.length = length;
		this.size = size;
		this.seed = seed;
	}

	static final double IN = 0.22, OUT = 0.3;

	/** How present the gesture is at {@code now}: 0 before and after, 1 in the middle, eased at both ends. */
	double weight(double now) {
		double t = now - start;
		if (t < 0) return 0;
		double end = end(), in = Stride.smooth(t / IN);
		double out = Double.isInfinite(end) || now < end ? 1 : Stride.smooth(1 - (now - end) / OUT);
		return Math.min(in, out);
	}

	double end() { return !Double.isNaN(release) ? release : start + length; }

	boolean over(double now) { return !Double.isInfinite(end()) && now >= end() + OUT; }

	/** Head offsets in degrees {yaw, pitch} at {@code now}: nods, shakes and talking. */
	double[] head(double now) {
		double t = now - start, w = weight(now);
		return switch (kind) {
			// Two nods: down quick, up slower, the second smaller.
			case NOD -> new double[] {0, w * size * 13 * Math.max(0, Math.sin(t * Math.PI * 2 / 0.42)) * (t < 0.42 ? 1 : 0.65)};
			case SHAKE -> new double[] {w * size * 17 * Math.sin(t * Math.PI * 2 / 0.46) * Math.exp(-t * 0.9), 0};
			// Talking: small irregular nods on the stresses, a slight turn now and then.
			case TALK -> new double[] {w * size * 3 * Math.sin(t * 1.7 + seed), w * size * (3.5 + 3.5 * Math.max(0, Math.sin(t * 9.1 + seed)) * Math.max(0, Math.sin(t * 2.3 + seed * 0.7)))};
			default -> new double[] {0, 0};
		};
	}

	/** Arm channels at {@code now} (NaN: leave vanilla); null for a head-only gesture. */
	float[] arms(double now) {
		if (!kind.arms() && kind != Kind.TALK) return null;
		float t = (float) (now - start) * 20, s = (float) size;
		float[] p = new float[CHANNELS];
		Arrays.fill(p, Float.NaN);
		p[HEAD_X] = p[HEAD_Z] = 0;
		switch (kind) {
			case WAVE -> {
				// The hand up beside the head, waving from the elbow.
				p[RAX] = -2.75f;
				p[RAY] = 0;
				p[RAZ] = -0.25f + 0.38f * s * sin(t * 0.55f);
				p[HEAD_Z] = 0.04f * sin(t * 0.55f);
			}
			case POINT -> {
				p[RAX] = -1.5f;
				p[RAY] = -0.1f;
				p[RAZ] = 0;
			}
			case SHRUG -> {
				float up = Math.min(1, t / 6f);
				p[RAX] = p[LAX] = -0.5f;
				p[RAY] = 0.35f;
				p[LAY] = -0.35f;
				p[RAZ] = 0.55f * up;
				p[LAZ] = -0.55f * up;
				p[HEAD_Z] = 0.18f * up;
				p[HEAD_X] = -0.05f;
			}
			case CHEER -> {
				p[RAX] = p[LAX] = -2.95f;
				p[RAY] = p[LAY] = 0;
				float pump = 0.18f * s * sin(t * 0.7f);
				p[RAZ] = -0.35f + pump;
				p[LAZ] = 0.35f - pump;
				p[HEAD_X] = -0.25f;
			}
			case FACEPALM -> {
				p[RAX] = -2.15f;
				p[RAY] = -0.55f;
				p[RAZ] = 0.1f;
				p[HEAD_X] = 0.38f;
				p[HEAD_Z] = 0.05f * sin(t * 0.2f);
			}
			case TYPE -> {
				float tap = 0.07f * s;
				p[RAX] = -1.15f + tap * sin(t * 1.3f);
				p[LAX] = -1.15f - tap * sin(t * 1.3f + 0.6f);
				p[RAY] = -0.14f;
				p[LAY] = 0.14f;
				p[RAZ] = p[LAZ] = 0;
				p[HEAD_X] = 0.12f;
			}
			case THINK -> {
				p[RAX] = -2.2f;
				p[RAY] = -0.45f;
				p[RAZ] = 0.3f;
				p[HEAD_X] = -0.2f;
				p[HEAD_Z] = 0.1f;
			}
			case HOLD -> {
				p[RAX] = -0.75f;
				p[RAY] = -0.12f;
				p[RAZ] = 0;
			}
			case TALK -> {
				// Talking with the hands, as in the prototype's SPEAK.
				p[RAX] = -0.7f + 0.28f * s * sin(t * 0.42f + seed);
				p[RAY] = -0.25f + 0.15f * sin(t * 0.31f);
				p[RAZ] = 0.1f;
				p[LAX] = -0.3f + 0.14f * s * sin(t * 0.36f + 1 + seed);
				p[LAY] = 0.1f;
				p[LAZ] = -0.1f;
			}
			default -> { return null; }
		}
		return p;
	}

	private static float sin(float x) { return (float) Math.sin(x); }

	/** Blends {@code pose} (NaN: vanilla) over the model's own {@code vanilla} channels by {@code w}. */
	static void blend(float[] out, float[] pose, float w) {
		for (int i = 0; i < CHANNELS; i++) {
			if (pose == null || Float.isNaN(pose[i])) continue;
			out[i] += (pose[i] - out[i]) * w;
		}
	}
}
