package io.github.alexandroslekkas.videocraft.api;

import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;

/**
 * Someone in the scene: the player, or a non-player character staged for the take. Actions find actors by id through
 * {@link ShotContext#actor(String)}. The director calls {@link #frame} every captured frame, before the actions, so an
 * actor can keep state across actions (keys held down, a hand mid-turn).
 */
public interface Actor {
	String id();

	/** The entity on the client, or null if it is not in the world right now. */
	Entity entity();

	/** Feet on the ground, without the bob of steps and jumps: what a camera follows. */
	default Vec3 ground() { Entity e = entity(); return e == null ? Vec3.ZERO : e.position(); }
	/** The way the body faces, in Minecraft yaw degrees. */
	default float heading() { Entity e = entity(); return e == null ? 0 : e.getYRot(); }
	/** Where the eyes are: for close-ups, and for others to look at. */
	default Vec3 head() { Entity e = entity(); return e == null ? Vec3.ZERO : e.getEyePosition(); }
	/** Blocks per second on the ground plane. */
	default Vec3 velocity() { return Vec3.ZERO; }

	default void frame(ShotContext shot) {}

	/** The shot is over: let go of keys, stop turning. The actor itself stays for the next shot. */
	default void cut(ShotContext shot) {}
}
