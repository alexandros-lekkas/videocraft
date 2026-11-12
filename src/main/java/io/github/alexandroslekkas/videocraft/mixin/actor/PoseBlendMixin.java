package io.github.alexandroslekkas.videocraft.mixin.actor;

import com.llamalad7.mixinextras.injector.wrapoperation.Operation;
import com.llamalad7.mixinextras.injector.wrapoperation.WrapOperation;
import io.github.alexandroslekkas.videocraft.actor.PoseBlend;
import net.minecraft.client.model.Model;
import net.minecraft.client.renderer.feature.ModelFeatureRenderer;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

/**
 * A puppet's model is posed through {@link PoseBlend} where the deferred draw poses it, so a sit or a lie-down eases
 * instead of popping. (The render layers, posed earlier in {@code LivingEntityRenderer.submit}, see {@link
 * PoseBlendSubmitMixin}.)
 */
@Mixin(ModelFeatureRenderer.class)
abstract class PoseBlendMixin {
	@WrapOperation(method = "prepareModel", at = @At(value = "INVOKE", target = "Lnet/minecraft/client/model/Model;setupAnim(Ljava/lang/Object;)V"))
	private void videocraft$blend(Model<?> model, Object state, Operation<Void> original) {
		PoseBlend.setup(model, state, s -> original.call(model, s));
	}
}
