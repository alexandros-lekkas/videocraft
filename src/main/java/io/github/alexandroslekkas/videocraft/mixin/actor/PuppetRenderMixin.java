package io.github.alexandroslekkas.videocraft.mixin.actor;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import io.github.alexandroslekkas.videocraft.actor.Puppets;
import net.minecraft.client.renderer.entity.EntityRenderDispatcher;
import net.minecraft.client.renderer.entity.EntityRenderer;
import net.minecraft.client.renderer.entity.state.EntityRenderState;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

/**
 * A puppet's entity is drawn at the puppet's own fraction of a tick (from the frame clock) rather than the game's,
 * so its interpolated position, turn and walk cycle in a frame are the same in every take.
 */
@Mixin(EntityRenderDispatcher.class)
abstract class PuppetRenderMixin {
	@WrapOperation(method = "extractEntity(Lnet/minecraft/world/entity/Entity;F)Lnet/minecraft/client/renderer/entity/state/EntityRenderState;",
		at = @At(value = "INVOKE", target = "Lnet/minecraft/client/renderer/entity/EntityRenderer;createRenderState(Lnet/minecraft/world/entity/Entity;F)Lnet/minecraft/client/renderer/entity/state/EntityRenderState;"))
	private EntityRenderState videocraft$puppetPhase(EntityRenderer<?, ?> renderer, Entity entity, float partialTicks, Operation<EntityRenderState> original) {
		return original.call(renderer, entity, Puppets.partial(entity, partialTicks));
	}
}
