package io.github.alexandroslekkas.videocraft.mixin.actor;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import io.github.alexandroslekkas.videocraft.actor.PoseBlend;
import net.minecraft.client.model.EntityModel;
import net.minecraft.client.renderer.entity.LivingEntityRenderer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

/** The render layers (a fox's held item, armour) are placed on the model as posed here: blended the same way. */
@Mixin(LivingEntityRenderer.class)
abstract class PoseBlendSubmitMixin {
	@WrapOperation(method = "submit(Lnet/minecraft/client/renderer/entity/state/LivingEntityRenderState;Lcom/mojang/blaze3d/vertex/PoseStack;Lnet/minecraft/client/renderer/SubmitNodeCollector;Lnet/minecraft/client/renderer/state/level/CameraRenderState;)V",
		at = @At(value = "INVOKE", target = "Lnet/minecraft/client/model/EntityModel;setupAnim(Ljava/lang/Object;)V"))
	private void videocraft$blend(EntityModel<?> model, Object state, Operation<Void> original) {
		PoseBlend.setup(model, state, s -> original.call(model, s));
	}
}
