package io.github.alexandroslekkas.videocraft.mixin.actor;

import io.github.alexandroslekkas.videocraft.actor.PuppetState;
import io.github.alexandroslekkas.videocraft.actor.Puppets;
import net.minecraft.client.renderer.entity.EntityRenderer;
import net.minecraft.client.renderer.entity.state.EntityRenderState;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Links each render state to its puppet (or to none), for the tint and the mannequin's poses. */
@Mixin(EntityRenderer.class)
abstract class PuppetExtractMixin {
	@Inject(method = "extractRenderState(Lnet/minecraft/world/entity/Entity;Lnet/minecraft/client/renderer/entity/state/EntityRenderState;F)V", at = @At("TAIL"))
	private void videocraft$linkPuppet(Entity entity, EntityRenderState state, float partialTicks, CallbackInfo info) {
		((PuppetState) state).videocraft$puppet(Puppets.of(entity));
	}
}
