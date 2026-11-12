package io.github.alexandroslekkas.videocraft;

import io.github.alexandroslekkas.videocraft.actor.Hand;
import io.github.alexandroslekkas.videocraft.api.Pose;
import io.github.alexandroslekkas.videocraft.camera.Operator;
import io.github.alexandroslekkas.videocraft.camera.Rigs;
import net.minecraft.world.phys.Vec3;

import java.util.Random;

/** Camera and hand math without Minecraft running: angles, easing, the operator spring, the hand's reproducibility. */
public final class RigChecks {
	public static void main(String[] args) {
		// Looking south (+z) is yaw 0, west (-x) is 90; looking down is positive pitch.
		Pose south = Pose.looking(Vec3.ZERO, new Vec3(0, 0, 5));
		PlanChecks.check(Math.abs(south.yaw()) < 1e-3 && Math.abs(south.pitch()) < 1e-3, "south is yaw 0: " + south);
		Pose west = Pose.looking(Vec3.ZERO, new Vec3(-5, 0, 0));
		PlanChecks.check(Math.abs(west.yaw() - 90) < 1e-3, "west is yaw 90: " + west);
		Pose down = Pose.looking(new Vec3(0, 5, 0), new Vec3(0, 0, 5));
		PlanChecks.check(Math.abs(down.pitch() - 45) < 1e-3, "down is +45 pitch: " + down);
		PlanChecks.check(Rigs.ease("smooth", 0.5) == 0.5 && Rigs.ease("linear", 2) == 1, "easing");
		// The operator settles on its target without overshoot.
		Operator op = new Operator(1);
		op.follow(new double[] {0}, 0.5, 1 / 60.0);
		double max = 0, at = 0;
		for (int i = 0; i < 600; i++) { at = op.follow(new double[] {10}, 0.5, 1 / 60.0)[0]; max = Math.max(max, at); }
		PlanChecks.check(Math.abs(at - 10) < 1e-3 && max <= 10 + 1e-9, "operator settles without overshoot: " + at + " max " + max);
		// The same seed gives the same hand.
		PlanChecks.check(java.util.Arrays.equals(Hand.keyTimes("hello world", new Random(7)), Hand.keyTimes("hello world", new Random(7))), "hand is reproducible");
		System.out.println("RigChecks PASS");
	}
}
