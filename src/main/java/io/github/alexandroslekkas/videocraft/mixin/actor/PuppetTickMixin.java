package io.github.alexandroslekkas.videocraft.mixin.actor;

import io.github.alexandroslekkas.videocraft.actor.Puppets;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * The level never ticks a puppet's entity: the puppet ticks it itself on the take's frame clock, so where it is and
 * what its animations do do not depend on how fast the game runs in real time. Everything else ticks as before.
 */
@Mixin(ClientLevel.class)
abstract class PuppetTickMixin {
	@Inject(method = "tickNonPassenger(Lnet/minecraft/world/entity/Entity;)V", at = @At("HEAD"), cancellable = true)
	private void videocraft$puppetTicksItself(Entity entity, CallbackInfo info) {
		if (Puppets.frozen(entity)) info.cancel();
	}
}
