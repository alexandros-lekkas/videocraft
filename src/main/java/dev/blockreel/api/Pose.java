package dev.blockreel.api;

import net.minecraft.world.phys.Vec3;

/** A camera for one frame: eye position and Minecraft angles (yaw grows clockwise from south, pitch grows downward). */
public record Pose(double x, double y, double z, float yaw, float pitch) {
	/** A camera at {@code eye} looking at {@code at}. */
	public static Pose looking(Vec3 eye, Vec3 at) {
		double dx = at.x - eye.x, dy = at.y - eye.y, dz = at.z - eye.z;
		float yaw = (float) (Math.toDegrees(Math.atan2(dz, dx)) - 90);
		float pitch = (float) -Math.toDegrees(Math.atan2(dy, Math.hypot(dx, dz)));
		return new Pose(eye.x, eye.y, eye.z, yaw, pitch);
	}

	public Vec3 eye() { return new Vec3(x, y, z); }
}
