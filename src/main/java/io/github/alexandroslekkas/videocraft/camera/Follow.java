package io.github.alexandroslekkas.videocraft.camera;

import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.phys.Vec3;

/**
 * How an operator keeps a subject: where its feet are on the ground (never its head, so steps and jumps do not bob
 * the camera) and which way it is going, both through a critically damped {@link Operator}, so the camera trails a
 * little, settles and never overshoots. The subject is looked up by id every frame (it may be staged after the rig is
 * made) and read only through {@link Actor}. Updated once per frame with a fixed step, so it is reproducible.
 */
final class Follow {
	/** Below this ground speed (blocks per second) a subject counts as standing. */
	static final double STANDING = 0.3;
	/** A subject that moves further than this in one frame (blocks) was placed, not walked. */
	static final double JUMP = 1.5;

	final String subject;
	final double lag, axisLag, riseLag;
	final boolean axisWhileStanding;
	private final Operator ground = new Operator(2), height = new Operator(1), axis = new Operator(2);
	private double levelY = Double.NaN;
	private Vec3 last;
	private Vec3 anchor = Vec3.ZERO, speed = Vec3.ZERO;
	private double heading;
	private boolean started;

	Follow(String subject, double lag, double axisLag, boolean axisWhileStanding) {
		this.subject = subject;
		this.lag = lag;
		this.axisLag = axisLag;
		this.riseLag = Math.max(lag, 0.4);
		this.axisWhileStanding = axisWhileStanding;
	}

	/** {@code subject} (required), {@code lag} (seconds the camera trails by). */
	static Follow of(Params p, double lag, double axisLag, boolean axisWhileStanding) {
		String id = p.string("subject");
		double l = p.number("lag", lag);
		if (l < 0 || l > 5) throw new IllegalArgumentException(p.where() + ": lag is 0 to 5 seconds, not " + l);
		return new Follow(id, l, axisLag, axisWhileStanding);
	}

	/** Reads the subject for this frame and moves the smoothed values one fixed step on. */
	void update(ShotContext shot) {
		Actor a = shot.actor(subject);
		double dt = 1.0 / shot.fps();
		Vec3 g = a.ground();
		// Put somewhere new by a cue (its start mark): the operator is there at once, as after a cut, instead of
		// swinging over from where the subject last was.
		if (last != null && g.distanceTo(last) > JUMP) {
			ground.cut();
			height.cut();
			axis.cut();
			levelY = Double.NaN;
			last = null;
			started = false;
		}
		// The player's own position jumps with it; take its height only from where it stands. Other actors give a
		// ground reference that already ignores the bob of steps and jumps.
		if (a.entity() instanceof Player p) {
			if (Double.isNaN(levelY) || p.onGround()) levelY = g.y;
		} else {
			levelY = g.y;
		}
		Vec3 v = a.velocity();
		if (v.horizontalDistanceSqr() < 1e-9 && last != null) v = g.subtract(last).scale(shot.fps());
		last = g;
		double moving = Math.hypot(v.x, v.z);
		// The way the subject is going: its body heading while it walks (and while it stands, if the rig swings).
		double h = Math.toRadians(a.heading());
		double[] dir = {-Math.sin(h), Math.cos(h)};
		double[] xz = ground.follow(new double[] {g.x, g.z}, lag, dt);
		double y = height.follow(new double[] {levelY}, riseLag, dt)[0];
		double[] ax;
		if (!started || moving >= STANDING || axisWhileStanding) ax = axis.follow(dir, axisLag, dt);
		else ax = axis.follow(new double[] {Math.cos(Math.toRadians(heading + 90)), Math.sin(Math.toRadians(heading + 90))}, axisLag, dt);
		started = true;
		anchor = new Vec3(xz[0], y, xz[1]);
		speed = new Vec3(v.x, 0, v.z);
		heading = Math.toDegrees(Math.atan2(ax[1], ax[0])) - 90;
	}

	/** The smoothed ground point under the subject. */
	Vec3 anchor() { return anchor; }

	/**
	 * The smoothed ground point moved on by the operator's own lag: where the subject is now on a steady walk (a
	 * critically damped follower trails a steady walk by speed × lag), still smooth. For rigs that must frame the
	 * subject where it is, not where it was (two_shot).
	 */
	Vec3 predicted() {
		double[] v = ground.speed();
		return anchor.add(v[0] * lag, 0, v[1] * lag);
	}

	/** The smoothed direction the subject goes, in Minecraft yaw degrees. */
	double heading() { return heading; }

	/** The subject's ground velocity this frame, blocks per second. */
	Vec3 velocity() { return speed; }

	/** Horizontal unit vector a Minecraft yaw faces (0 is south, +z; 90 is west, -x). */
	static Vec3 forward(double yaw) {
		double r = Math.toRadians(yaw);
		return new Vec3(-Math.sin(r), 0, Math.cos(r));
	}

	/** Horizontal unit vector to the right of someone facing {@code yaw}. */
	static Vec3 right(double yaw) {
		double r = Math.toRadians(yaw);
		return new Vec3(-Math.cos(r), 0, -Math.sin(r));
	}
}
