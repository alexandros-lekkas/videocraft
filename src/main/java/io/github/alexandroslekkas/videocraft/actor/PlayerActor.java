package io.github.alexandroslekkas.videocraft.actor;

import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.ClientInput;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.util.Mth;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.player.Input;
import net.minecraft.world.item.component.SwingAnimation;
import net.minecraft.world.level.block.DoorBlock;
import net.minecraft.world.phys.Vec2;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.List;

/**
 * The local player, played rather than animated (DESIGN.md, "Actors"): the script holds movement keys through a
 * {@link Keys ClientInput} the game reads exactly as it reads the keyboard, and a {@link Hand.Look} turns the view every
 * frame, so acceleration, the walk cycle, sprint and jumps are the game's own. Ported from T3 Craft's DemoRecorder (MIT,
 * same owner). Idle until the script first gives it something to do; then it keeps its view on the hand model.
 *
 * <p>Not frame-exact between takes: the player is simulated on the client's own ticks, whose phase against the frame
 * clock is set by real time at the start of the take, so positions can differ by a fraction of a tick.
 */
public final class PlayerActor implements Actor {
	private final Minecraft mc;
	private final Keys keys = new Keys();
	private Hand.Look look;
	private Walk walk;
	private boolean driving;
	private long seed = 1;

	PlayerActor(Minecraft mc) { this.mc = mc; }

	void seed(long seed) { this.seed = seed; }

	@Override public String id() { return "player"; }
	@Override public Entity entity() { return mc.player; }

	@Override
	public Vec3 velocity() {
		LocalPlayer p = mc.player;
		return p == null ? Vec3.ZERO : new Vec3(p.getDeltaMovement().x * 20, 0, p.getDeltaMovement().z * 20);
	}

	/** Takes the player over: from now on the script's keys and the hand's view. */
	private LocalPlayer drive() {
		LocalPlayer p = mc.player;
		if (p == null) throw new IllegalStateException("no player in the world");
		if (!driving || look == null) {
			driving = true;
			look = new Hand.Look(seed ^ 0x5DEECE66DL, p.getYRot(), p.getXRot());
			look.fidget(0.8);
		}
		if (p.input != keys) p.input = keys;
		return p;
	}

	@Override
	public void frame(ShotContext shot) {
		LocalPlayer p = mc.player;
		if (!driving || p == null) return;
		if (p.input != keys) p.input = keys;
		if (walk != null) {
			walk.frame(p);
			if (walk.arrived) {
				walk = null;
				keys.release();
			}
		}
		// The view turns only where the game would let a mouse turn it: never with a screen open.
		if (mc.gui.screen() == null) {
			double[] at = look.step(1.0 / shot.fps());
			float yaw = (float) at[0], pitch = (float) at[1];
			p.setYRot(yaw);
			p.setXRot(pitch);
			p.setYHeadRot(yaw);
			p.yRotO = yaw;
			p.xRotO = pitch;
			p.yHeadRotO = yaw;
		}
	}

	@Override
	public void cut(ShotContext shot) {
		keys.release();
		walk = null;
	}

	// ---- What actions ask of the player ----

	void walk(List<Vec3> path, boolean sprint, Vec3 face) {
		drive();
		walk = new Walk(path, sprint, face);
	}

	boolean walking() { return walk != null; }

	void stop() { walk = null; keys.release(); }

	/** Turns the view to look at {@code at} the way a hand moves a mouse: one quick movement, a correction or two. */
	void turnTo(Vec3 at, double tolerance) {
		LocalPlayer p = drive();
		look.turnTo(yawTo(p.getEyePosition(), at), pitchTo(p.getEyePosition(), at), tolerance);
	}

	void turnTo(double yaw, double pitch) {
		drive();
		look.turnTo(yaw, pitch, 0.5);
	}

	/** Keeps the eyes on a moving target, as a person tracks it: glances that catch up now and then. */
	void follow(Vec3 at) {
		LocalPlayer p = drive();
		look.follow(2.5);
		look.aim(yawTo(p.getEyePosition(), at), pitchTo(p.getEyePosition(), at), 0, 0);
	}

	boolean turning() { return look != null && look.moving(); }

	void jump() { drive(); keys.jump = 2; }

	void sneak(boolean on) { drive(); keys.sneak = on; }

	void swing() { drive().swing(InteractionHand.MAIN_HAND, SwingAnimation.DEFAULT, false); }

	static float yawTo(Vec3 from, Vec3 at) { return (float) Math.toDegrees(Math.atan2(at.z - from.z, at.x - from.x)) - 90; }

	static float pitchTo(Vec3 from, Vec3 at) { return (float) -Math.toDegrees(Math.atan2(at.y - from.y, Math.hypot(at.x - from.x, at.z - from.z))); }

	private static double flat(Vec3 a, Vec3 b) { return Math.hypot(a.x - b.x, a.z - b.z); }

	private static Vec3 mix(Vec3 a, Vec3 b, double k) { return a.add(b.subtract(a).scale(k)); }

	/** The keys the script holds down; the game reads them exactly as it reads the keyboard. */
	static final class Keys extends ClientInput {
		boolean forward, back, left, right, sneak, sprint;
		int jump;

		@Override
		public void tick() {
			keyPresses = new Input(forward, back, left, right, jump > 0, sneak, sprint);
			if (jump > 0) jump--;
			moveVector = new Vec2((left ? 1 : 0) - (right ? 1 : 0), (forward ? 1 : 0) - (back ? 1 : 0)).normalized();
		}

		void release() {
			forward = back = left = right = sneak = sprint = false;
			jump = 0;
		}
	}

	/**
	 * Walking somewhere the way a person does: looking at a point a few blocks further along the route (so corners are
	 * cut and the path bends), holding forward, sprinting on the straights, letting go of sprint and then of forward
	 * before the mark and coasting the rest. With something to face, the last blocks are walked looking at it, sideways
	 * if need be, so the player arrives turned to it instead of stopping and then swivelling. A ledge the stride does
	 * not clear is jumped; never a door.
	 */
	private final class Walk {
		final List<Vec3> path;
		final boolean sprint;
		final Vec3 face;
		int leg;
		boolean arrived, turned;

		Walk(List<Vec3> path, boolean sprint, Vec3 face) {
			this.path = new ArrayList<>(path);
			this.sprint = sprint;
			this.face = face;
			look.follow(2.5);
		}

		void frame(LocalPlayer p) {
			Vec3 at = p.position();
			while (leg < path.size() - 1 && flat(at, path.get(leg)) < 1.1) leg++;
			double remaining = flat(at, path.get(leg));
			for (int i = leg; i < path.size() - 1; i++) remaining += flat(path.get(i), path.get(i + 1));
			double ahead = sprint ? 3.0 : 2.0;
			Vec3 from = at, aim = path.getLast();
			for (int i = leg; i < path.size(); i++) {
				double length = flat(from, path.get(i));
				if (ahead <= length || i == path.size() - 1) { aim = mix(from, path.get(i), length < 1e-6 ? 1 : Math.min(1, ahead / length)); break; }
				ahead -= length;
				from = path.get(i);
			}
			float heading = yawTo(at, aim);
			boolean facing = face != null && remaining < 3.4;
			if (facing) {
				Vec3 eyes = p.getEyePosition();
				if (!turned) { turned = true; look.turnTo(yawTo(eyes, face), pitchTo(eyes, face), 3); }
				else if (!look.moving()) { look.follow(2.5); look.aim(yawTo(eyes, face), pitchTo(eyes, face), 0, 0); }
			} else if (flat(at, aim) > 0.4) look.aim(heading, 4, 0, 0);
			double off = Mth.wrapDegrees(heading - p.getYRot()), away = Math.abs(off), speed = p.getDeltaMovement().horizontalDistance();
			if (remaining < 0.3 + speed * 1.6) {
				keys.forward = keys.back = keys.left = keys.right = keys.sprint = false;
				if (speed < 0.03) arrived = true;
				return;
			}
			if (facing) {
				keys.forward = away < 67.5;
				keys.back = away > 112.5;
				keys.left = off < -22.5 && off > -157.5;
				keys.right = off > 22.5 && off < 157.5;
				keys.sprint = false;
			} else {
				keys.forward = away < 80;
				keys.back = keys.left = keys.right = false;
				keys.sprint = sprint && away < 55 && remaining > 2.6;
			}
			if (!p.onGround()) return;
			if (p.horizontalCollision) { keys.jump = 2; return; }
			// A block in the way of the stride: jump it a moment before reaching it.
			if (speed > 0.08) {
				Vec3 v = p.getDeltaMovement();
				double reach = keys.sprint ? 1.3 : 0.9;
				BlockPos block = BlockPos.containing(at.x + v.x / speed * reach, at.y + 0.1, at.z + v.z / speed * reach);
				var state = mc.level.getBlockState(block);
				var shape = state.getCollisionShape(mc.level, block);
				if (!shape.isEmpty() && shape.max(net.minecraft.core.Direction.Axis.Y) > 0.6 && !(state.getBlock() instanceof DoorBlock)
					&& mc.level.getBlockState(block.above()).getCollisionShape(mc.level, block.above()).isEmpty()) keys.jump = 2;
			}
		}
	}
}
