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
		var puppet = Puppets.of(entity);
		((PuppetState) state).videocraft$puppet(puppet);
		// Shot preparation draws a puppet without ticking it, and a mannequin only takes its finished skin lookup in its tick.
		if (puppet != null && entity instanceof ClientMannequinAccess m && m.videocraft$skinLookup() != null && m.videocraft$skinLookup().isDone()) {
			m.videocraft$skinLookup().getNow(java.util.Optional.empty()).ifPresent(m::videocraft$setSkin);
			m.videocraft$setSkinLookup(null);
		}
	}
}
