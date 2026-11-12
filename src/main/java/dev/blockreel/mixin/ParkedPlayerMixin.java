package dev.blockreel.mixin;

import dev.blockreel.director.Director;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.culling.Frustum;
import net.minecraft.client.renderer.entity.EntityRenderDispatcher;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * While an unseen operator holds the camera, the local player (a spectator parked at the camera so its chunks stay
 * loaded) is not drawn: in 26.3 the game does draw the local player, as a spectator's head, once the camera entity is
 * another entity. No take: nothing changes.
 */
@Mixin(EntityRenderDispatcher.class)
abstract class ParkedPlayerMixin {
	@Inject(method = "shouldRender", at = @At("HEAD"), cancellable = true)
	private <E extends Entity> void blockreel$hideParked(E entity, Frustum frustum, double x, double y, double z, float partialTick, CallbackInfoReturnable<Boolean> info) {
		if (Director.hidesPlayer() && entity == Minecraft.getInstance().player) info.setReturnValue(false);
	}
}
