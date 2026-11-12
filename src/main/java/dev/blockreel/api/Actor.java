package dev.blockreel.api;

import net.minecraft.world.entity.Entity;

/**
 * Someone in the scene: the player, or a non-player character staged for the take. Actions find actors by id through
 * {@link ShotContext#actor(String)}. The director calls {@link #frame} every captured frame, before the actions, so an
 * actor can keep state across actions (keys held down, a hand mid-turn).
 */
public interface Actor {
	String id();

	/** The entity on the client, or null if it is not in the world right now. */
	Entity entity();

	default void frame(ShotContext shot) {}

	/** The shot is over: let go of keys, stop turning. The actor itself stays for the next shot. */
	default void cut(ShotContext shot) {}
}
