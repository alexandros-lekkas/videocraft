package dev.blockreel.actor;

import dev.blockreel.api.Actor;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.Entity;

/**
 * The local player as an actor. Owned by workstream (b): this is where the held keys (a ClientInput the script
 * drives), the {@link Hand} turning the view each frame, and the walk that follows a path belong.
 */
public final class PlayerActor implements Actor {
	private final Minecraft mc;

	PlayerActor(Minecraft mc) { this.mc = mc; }

	@Override public String id() { return "player"; }
	@Override public Entity entity() { return mc.player; }
}
