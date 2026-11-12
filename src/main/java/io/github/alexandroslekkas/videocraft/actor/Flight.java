package io.github.alexandroslekkas.videocraft.actor;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * Where a flying puppet is, tick by tick: a bee, a parrot, an allay, a bat, a chicken's flap-glide. Pure arithmetic,
 * no Minecraft classes; seconds, blocks, Minecraft yaw degrees. Flight never falls: nothing here has gravity.
 *
 * <p>A flyer is always in one of five motions, each a function of the time since it began:
 * <ul>
 *   <li><b>route</b> ({@code fly}): along an {@link AirPath} at a cruise speed, eased in and out with no lurch, then
 *       it hovers where it arrived;</li>
 *   <li><b>hover</b>: near a point, with a slow seeded drift in a small radius and a gentle bob;</li>
 *   <li><b>orbit</b> ({@code swarm}): round an anchor (an actor, or a point) on a sphere of its own radius whose plane
 *       of flight tilts and turns slowly. Every member of one swarm has its own radius, so two of them are never nearer
 *       than the gap between their radii; the tilt is held low enough that the flyer always stays clear of the
 *       anchor's body (an upright cylinder) and above the floor;</li>
 *   <li><b>land</b>: to a spot (a block top, or a place on an actor, which may move), over it and down onto it;</li>
 *   <li><b>perch</b>: sitting on that spot (wings still), riding along with the actor it sits on.</li>
 * </ul>
 * A change of motion never jumps: the difference between where the flyer is (and how it moves) and where the new
 * motion begins is carried as an offset that dies away on a critically damped spring, so position and velocity are
 * continuous. The attitude comes from the motion: the heading is the direction of travel, the body banks into turns
 * (as a coordinated turn: tan bank = speed x turn rate / g) and pitches with climbs and dives, all eased.
 */
public final class Flight {
	static final double G = 9.8;
	/** The fastest a change of motion closes the gap to the new motion, blocks a second. */
	static final double CATCH_UP = 2.6;
	/** A flyer's body on the anchor it circles or sits on: feet, heading, and the size of the body to keep clear of. */
	public interface Anchor {
		double[] feet();

		double yaw();

		double width();

		double height();
	}

	/** One of the five motions: where the flyer wants to be {@code t} seconds after it began. */
	private interface Motion {
		double[] at(double t);

		default boolean done(double t) { return false; }

		default boolean airborne() { return true; }
	}

	private final double size;
	private double x, y, z, vx, vy, vz, t, start;
	private double ox, oy, oz, ovx, ovy, ovz, omega = 5;
	private Motion motion;
	private Anchor keepOut;
	private double clear, half;
	private double bank, pitch, groundY, lastYaw = Double.NaN, turnRate;
	private double bankScale = 1, faceYaw = Double.NaN;
	private boolean arrived;

	/**
	 * A flyer hovering at {x, y, z} (its feet), its body {@code size} blocks across (the gaps of a swarm and the clear
	 * space around an anchor scale with it).
	 */
	public Flight(double x, double y, double z, double size, Random random) {
		this.x = x;
		this.y = y;
		this.z = z;
		this.size = Math.max(0.1, size);
		this.groundY = y;
		this.arrived = true;
		this.motion = hoverMotion(new double[] {x, y, z}, 0.25 * scaleOf(), 0.06 * scaleOf(), random);
	}

	private double scaleOf() { return Math.min(1.5, Math.max(0.35, size / 0.7)); }

	// ---- Motions ----

	/**
	 * Fly from where it is through {@code points} at {@code speed} blocks a second, easing up over {@code accel} and
	 * down over {@code arrive} seconds; {@code bank} scales the banking (0 flies level). Then it hovers there.
	 */
	public void fly(List<double[]> points, double speed, double accel, double arrive, double bank, Random random) {
		List<double[]> all = new ArrayList<>();
		all.add(new double[] {x, y, z});
		all.addAll(points);
		AirPath path = AirPath.through(all);
		bankScale = bank;
		faceYaw = Double.NaN;
		arrived = false;
		double[] end = path.at(path.length());
		Random after = new Random(random.nextLong());
		Profile profile = new Profile(path.length(), speed, accel, arrive);
		begin(new Motion() {
			@Override public double[] at(double t) { return path.at(profile.at(t)); }

			@Override public boolean done(double t) { return t >= profile.time(); }
		}, 5, null);
		then = () -> {
			arrived = true;
			begin(hoverMotion(end, 0.18 * scaleOf(), 0.05 * scaleOf(), after), 5, null);
		};
	}

	/** Hover near {@code center}: a seeded drift within {@code radius} blocks and a bob of {@code bob} blocks. */
	public void hover(double[] center, double radius, double bob, double faceYaw, Random random) {
		this.faceYaw = faceYaw;
		begin(hoverMotion(center, radius, bob, random), 4, null);
		arrived = true;
	}

	private Motion hoverMotion(double[] c, double radius, double bob, Random random) {
		// Two slow incommensurate sines per axis for the drift, one quicker one for the bob: never a visible loop.
		double f1 = 0.13 + random.nextDouble() * 0.08, f2 = 0.29 + random.nextDouble() * 0.12, fb = 0.55 + random.nextDouble() * 0.3;
		double g1 = 0.11 + random.nextDouble() * 0.08, g2 = 0.31 + random.nextDouble() * 0.12;
		double p1 = random.nextDouble() * 6.283, p2 = random.nextDouble() * 6.283, pb = random.nextDouble() * 6.283;
		double q1 = random.nextDouble() * 6.283, q2 = random.nextDouble() * 6.283;
		return t -> {
			double w = 2 * Math.PI;
			// Each axis within radius / sqrt 2, so the drift never leaves a disc of the radius.
			double dx = (Math.sin(w * f1 * t + p1) + 0.5 * Math.sin(w * f2 * t + p2)) / 1.5 * radius * 0.7071;
			double dz = (Math.sin(w * g1 * t + q1) + 0.5 * Math.sin(w * g2 * t + q2)) / 1.5 * radius * 0.7071;
			double dy = Math.sin(w * fb * t + pb) * bob + Math.sin(w * f1 * 0.7 * t + q2) * bob * 0.4;
			return new double[] {c[0] + dx, c[1] + dy, c[2] + dz};
		};
	}

	/** The clear horizontal distance a flyer of this size keeps from the axis of a body {@code width} blocks across. */
	public double clearance(double width) {
		// The body's square footprint (its corners at width/sqrt 2) plus the flyer's own half-width and a margin.
		return width * 0.7072 + size * 0.5 + 0.12;
	}

	/**
	 * The radii of a swarm of {@code n} round a body {@code width} wide: the first clear of it, the others a gap apart
	 * (at least most of a flyer's width), spread out to {@code outer} when that is further.
	 */
	public double[] lanes(int n, double width, double inner, double outer) {
		double r0 = Math.max(clearance(width) + 0.1 + 0.08 * scaleOf(), inner);
		double gap = Math.max(size * 0.85, n > 1 ? (outer - r0) / (n - 1) : 0);
		double[] out = new double[n];
		for (int i = 0; i < n; i++) out[i] = r0 + i * gap;
		return out;
	}

	/**
	 * Circle {@code anchor} (or the fixed point {@code point} when it is null) at {@code radius} blocks from a centre
	 * {@code lift} blocks above its feet, at about {@code speed} blocks a second, the plane of flight tilting and turning
	 * slowly. With an anchor, the flyer is kept out of its body ({@link #clearance}) at every tick, also on the way in.
	 */
	public void orbit(Anchor anchor, double[] point, double radius, double lift, double speed, double gap, Random random) {
		double width = anchor == null ? 0 : anchor.width();
		double clearR = anchor == null ? 0 : clearance(width);
		double breathe = Math.min(0.06 * scaleOf(), gap * 0.12);
		double rMin = radius - breathe;
		// The highest tilt that keeps the flyer clear of the body (horizontal distance r cos(tilt) >= clearance) and
		// above the floor (the centre's lift minus r sin(tilt) >= half the flyer's height and a margin).
		double byBody = clearR <= 0 ? Math.toRadians(55) : Math.acos(Math.min(1, (clearR + 0.03) / rMin));
		double floor = (lift - size * 0.45 - 0.12) / (radius + breathe);
		double byFloor = floor <= 0 ? 0 : Math.asin(Math.min(1, floor));
		double maxTilt = Math.max(0, Math.min(Math.toRadians(55), Math.min(byBody, byFloor)) - 0.02);
		double dir = random.nextBoolean() ? 1 : -1;
		double w = dir * speed * (0.85 + random.nextDouble() * 0.3) / radius;
		double theta0 = random.nextDouble() * 6.283, node0 = random.nextDouble() * 6.283;
		double precess = (random.nextBoolean() ? 1 : -1) * (0.25 + random.nextDouble() * 0.35);
		double tiltF = 0.07 + random.nextDouble() * 0.08, tiltP = random.nextDouble() * 6.283;
		double brF = 0.4 + random.nextDouble() * 0.4, brP = random.nextDouble() * 6.283;
		double[] fixed = point == null ? null : point.clone();
		bankScale = 1;
		faceYaw = Double.NaN;
		arrived = true;
		begin(t -> {
			double[] c = centre(anchor, fixed, lift);
			double tilt = maxTilt * (0.45 + 0.55 * (0.5 + 0.5 * Math.sin(2 * Math.PI * tiltF * t + tiltP)));
			double node = node0 + precess * t, theta = theta0 + w * t;
			double r = radius + breathe * Math.sin(2 * Math.PI * brF * t + brP);
			// The plane's normal leans by `tilt` toward `node`; e1 is level in the plane, e2 = n x e1.
			double si = Math.sin(tilt), ci = Math.cos(tilt), sn = Math.sin(node), cn = Math.cos(node);
			double nx = si * cn, ny = ci, nz = si * sn;
			double e1x = -sn, e1y = 0, e1z = cn;
			double e2x = ny * e1z - nz * e1y, e2y = nz * e1x - nx * e1z, e2z = nx * e1y - ny * e1x;
			double ct = Math.cos(theta), st = Math.sin(theta);
			return new double[] {c[0] + r * (ct * e1x + st * e2x), c[1] + r * (ct * e1y + st * e2y), c[2] + r * (ct * e1z + st * e2z)};
		}, 3.2, anchor);
	}

	private static double[] centre(Anchor anchor, double[] fixed, double lift) {
		double[] f = anchor == null ? fixed : anchor.feet();
		return new double[] {f[0], f[1] + lift, f[2]};
	}

	/**
	 * Land on {@code anchor} at {@code local} = {front, right, up} in its frame (riding along afterwards), or, with no
	 * anchor, on the fixed {@code spot} (a block top). It comes in over the spot and settles down onto it.
	 */
	public void land(Anchor anchor, double[] local, double[] spot, double speed, Random random) {
		double[] s0 = anchor == null ? spot.clone() : onAnchor(anchor, local);
		double[] from = {x, y, z};
		double up = 0.45 + size * 0.6;
		// Come in from the side the spot is on (off the anchor's axis), so the approach is not through its body.
		double ax = 0, az = 0;
		if (anchor != null) {
			double[] f = anchor.feet();
			double dx = s0[0] - f[0], dz = s0[2] - f[2], d = Math.hypot(dx, dz);
			if (d > 0.05) { ax = dx / d * 0.5; az = dz / d * 0.5; }
		}
		List<double[]> pts = new ArrayList<>();
		pts.add(from);
		if (AirPath.dist(from, s0) > up + 0.3) pts.add(new double[] {s0[0] + ax, s0[1] + up, s0[2] + az});
		pts.add(new double[] {s0[0], s0[1] + Math.min(0.2, up * 0.4), s0[2]});
		pts.add(s0);
		AirPath path = AirPath.through(pts);
		Profile profile = new Profile(path.length(), speed, 0.4, 0.9);
		bankScale = 1;
		faceYaw = Double.NaN;
		arrived = false;
		begin(new Motion() {
			@Override
			public double[] at(double t) {
				double s = profile.at(t), k = path.length() < 1e-6 ? 1 : s / path.length();
				double[] p = path.at(s), now = anchor == null ? s0 : onAnchor(anchor, local);
				return new double[] {p[0] + (now[0] - s0[0]) * k, p[1] + (now[1] - s0[1]) * k, p[2] + (now[2] - s0[2]) * k};
			}

			@Override public boolean done(double t) { return t >= profile.time(); }
		}, 5, null);
		then = () -> {
			arrived = true;
			begin(new Motion() {
				@Override public double[] at(double t) { return anchor == null ? s0 : onAnchor(anchor, local); }

				@Override public boolean airborne() { return false; }
			}, 14, null);
			perchAnchor = anchor;
		};
		perchAnchor = null;
	}

	private Anchor perchAnchor;

	/** A point in an anchor's own frame ({front, right, up} from its feet along its heading) in the world. */
	static double[] onAnchor(Anchor a, double[] local) {
		double[] f = a.feet();
		double yaw = Math.toRadians(a.yaw());
		// Minecraft yaw: forward is (-sin, cos); right of forward is (-cos, -sin).
		double fx = -Math.sin(yaw), fz = Math.cos(yaw), rx = -Math.cos(yaw), rz = -Math.sin(yaw);
		return new double[] {f[0] + fx * local[0] + rx * local[1], f[1] + local[2], f[2] + fz * local[0] + rz * local[1]};
	}

	/** Put it at {x, y, z} at once, hovering there (a jump cut). */
	public void place(double[] at, Random random) {
		x = at[0];
		y = at[1];
		z = at[2];
		vx = vy = vz = 0;
		ox = oy = oz = ovx = ovy = ovz = 0;
		groundY = y;
		bank = pitch = 0;
		lastYaw = Double.NaN;
		then = null;
		motion = hoverMotion(at, 0.18 * scaleOf(), 0.05 * scaleOf(), random);
		double[] p0 = motion.at(0);
		ox = x - p0[0];
		oy = y - p0[1];
		oz = z - p0[2];
		start = t;
		keepOut = null;
		perchAnchor = null;
		arrived = true;
	}

	private Runnable then;

	private void begin(Motion m, double omega, Anchor keepOut) {
		then = null;
		double dt = Puppet.TICK;
		double[] p0 = m.at(0), pm = m.at(-dt);
		ox = x - p0[0];
		oy = y - p0[1];
		oz = z - p0[2];
		ovx = vx - (p0[0] - pm[0]) / dt;
		ovy = vy - (p0[1] - pm[1]) / dt;
		ovz = vz - (p0[2] - pm[2]) / dt;
		this.omega = omega;
		this.motion = m;
		this.keepOut = keepOut;
		this.clear = keepOut == null ? 0 : clearance(keepOut.width());
		this.half = size * 0.5;
		start = t;
	}

	// ---- One tick ----

	/** One tick of {@code dt} seconds. */
	public void step(double dt) {
		t += dt;
		double mt = t - start;
		double[] p = motion.at(mt);
		double[] sx = Heading.spring(ox, ovx, 0, omega, dt), sy = Heading.spring(oy, ovy, 0, omega, dt), sz = Heading.spring(oz, ovz, 0, omega, dt);
		// The way in to a far motion (a swarm joined from across the room) is flown at most CATCH_UP blocks a second
		// faster than the motion itself: the spring may slow the offset as it likes, but not hurl it.
		double mx = (sx[0] - ox) / dt, my = (sy[0] - oy) / dt, mz = (sz[0] - oz) / dt;
		double mean = Math.sqrt(mx * mx + my * my + mz * mz), was = Math.sqrt(ovx * ovx + ovy * ovy + ovz * ovz);
		double cap = Math.max(CATCH_UP, was);
		if (mean > cap) {
			double k = cap / mean;
			ox += mx * k * dt; ovx = mx * k;
			oy += my * k * dt; ovy = my * k;
			oz += mz * k * dt; ovz = mz * k;
		} else {
			ox = sx[0]; ovx = sx[1];
			oy = sy[0]; ovy = sy[1];
			oz = sz[0]; ovz = sz[1];
		}
		double nx = p[0] + ox, ny = p[1] + oy, nz = p[2] + oz;
		if (keepOut != null) {
			double[] q = keepClear(keepOut, nx, ny, nz);
			nx = q[0];
			ny = q[1];
			nz = q[2];
		}
		vx = (nx - x) / dt;
		vy = (ny - y) / dt;
		vz = (nz - z) / dt;
		x = nx;
		y = ny;
		z = nz;
		attitude(dt);
		if (then != null && motion.done(mt)) {
			Runnable next = then;
			then = null;
			next.run();
		}
	}

	/** {x, y, z} moved out of the anchor's body (an upright cylinder of the clearance radius), if it was inside. */
	double[] keepClear(Anchor a, double px, double py, double pz) {
		double[] f = a.feet();
		if (py < f[1] - half - 0.05 || py > f[1] + a.height() + half + 0.05) return new double[] {px, py, pz};
		double dx = px - f[0], dz = pz - f[2], d = Math.hypot(dx, dz);
		if (d >= clear) return new double[] {px, py, pz};
		if (d < 1e-6) { dx = x - f[0]; dz = z - f[2]; d = Math.hypot(dx, dz); if (d < 1e-6) { dx = 1; dz = 0; d = 1; } }
		return new double[] {f[0] + dx / d * clear, py, f[2] + dz / d * clear};
	}

	private void attitude(double dt) {
		double hs = Math.hypot(vx, vz);
		boolean flying = motion.airborne();
		double wantBank = 0, wantPitch = 0;
		if (flying && hs > 0.3) {
			double yaw = Path.yaw(vx, vz);
			double rate = Double.isNaN(lastYaw) ? 0 : Math.toRadians(Path.wrap(yaw - lastYaw)) / dt;
			lastYaw = yaw;
			turnRate += (rate - turnRate) * (1 - Math.exp(-dt / 0.1));
			// A coordinated turn banks by atan(v w / g): right wing down (positive) turning right (yaw increasing).
			wantBank = Math.toDegrees(Math.atan(hs * turnRate / G)) * bankScale;
			wantPitch = Math.toDegrees(Math.atan2(vy, Math.max(hs, 0.6))) * 0.7;
		} else {
			turnRate *= Math.exp(-dt / 0.1);
		}
		wantBank = Math.max(-40, Math.min(40, wantBank));
		wantPitch = Math.max(-35, Math.min(35, wantPitch));
		bank += (wantBank - bank) * (1 - Math.exp(-dt / 0.15));
		pitch += (wantPitch - pitch) * (1 - Math.exp(-dt / 0.2));
		// The cameras' reference: the height without the bob and the quick moves, eased over about 0.4 s.
		groundY += (y - groundY) * (1 - Math.exp(-dt / 0.4));
		if (Math.abs(y - groundY) > 4) groundY = y;
	}

	// ---- What it reads ----

	public double x() { return x; }

	public double y() { return y; }

	public double z() { return z; }

	public double[] velocity() { return new double[] {vx, vy, vz}; }

	/** Height for cameras: the flight's height eased, without its bob. */
	public double groundY() { return groundY; }

	/** Degrees of bank, right wing down positive. */
	public double bank() { return bank; }

	/** Degrees of pitch, nose up positive. */
	public double pitch() { return pitch; }

	/** Whether it is in the air (not perched): wings beat, the ground is not under it. */
	public boolean airborne() { return motion.airborne(); }

	/** A fly or a landing has arrived (a hover, an orbit and a perch have from the start). */
	public boolean arrived() { return arrived; }

	/**
	 * The heading it wants: the direction of travel when it moves, else the hover's facing when one is given; NaN
	 * keeps the heading it has (and, perched on an actor, the puppet turns with it).
	 */
	public double yawGoal() {
		if (!motion.airborne()) return Double.NaN;
		if (Math.hypot(vx, vz) > 0.35) return Path.yaw(vx, vz);
		return faceYaw;
	}

	/** The actor it sits on, while perched on one; else null. */
	public Anchor perchedOn() { return motion.airborne() ? null : perchAnchor; }

	/** Holds a heading while hovering (NaN: none). */
	public void face(double yaw) { faceYaw = yaw; }

	/**
	 * An eased speed profile along a distance: up to cruise over {@code accel} seconds (a smoothstep in speed), a
	 * cruise, down to rest over {@code arrive} seconds. A distance too short for the cruise lowers the top speed.
	 */
	static final class Profile {
		private final double length, v, ta, tb, tc;

		Profile(double length, double speed, double accel, double arrive) {
			this.length = length;
			double a = Math.max(0.05, accel), b = Math.max(0.05, arrive);
			double cruise = Math.max(0.05, speed);
			double ramp = cruise * (a + b) / 2;
			if (length < ramp) {
				cruise = 2 * length / (a + b);
				this.tc = 0;
			} else {
				this.tc = (length - ramp) / cruise;
			}
			this.v = cruise;
			this.ta = a;
			this.tb = b;
		}

		double time() { return ta + tc + tb; }

		/** The distance along at {@code t} seconds. */
		double at(double t) {
			if (length <= 0 || t <= 0) return 0;
			if (t < ta) { double u = t / ta; return v * ta * (u * u * u - u * u * u * u / 2); }
			if (t < ta + tc) return v * ta / 2 + v * (t - ta);
			if (t < time()) { double w = (time() - t) / tb; return length - v * tb * (w * w * w - w * w * w * w / 2); }
			return length;
		}

		double speed() { return v; }
	}
}
