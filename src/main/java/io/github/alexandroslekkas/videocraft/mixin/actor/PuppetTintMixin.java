package io.github.alexandroslekkas.videocraft.mixin.actor;

import io.github.alexandroslekkas.videocraft.actor.PuppetState;
import com.llamalad7.mixinextras.injector.ModifyExpressionValue;
import com.llamalad7.mixinextras.sugar.Local;
import io.github.alexandroslekkas.videocraft.actor.Puppet;
import net.minecraft.client.renderer.entity.LivingEntityRenderer;
import net.minecraft.client.renderer.entity.state.LivingEntityRenderState;
import net.minecraft.util.ARGB;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

/** {@code tint = "#rrggbb"}: a puppet's model is multiplied by a colour, so a slate-blue goat needs no texture file. */
@Mixin(LivingEntityRenderer.class)
abstract class PuppetTintMixin {
	@ModifyExpressionValue(method = "submit(Lnet/minecraft/client/renderer/entity/state/LivingEntityRenderState;Lcom/mojang/blaze3d/vertex/PoseStack;Lnet/minecraft/client/renderer/SubmitNodeCollector;Lnet/minecraft/client/renderer/state/level/CameraRenderState;)V",
		at = @At(value = "INVOKE", target = "Lnet/minecraft/client/renderer/entity/LivingEntityRenderer;getModelTint(Lnet/minecraft/client/renderer/entity/state/LivingEntityRenderState;)I"))
	private int videocraft$tint(int tint, @Local(argsOnly = true) LivingEntityRenderState state) {
		Puppet p = ((PuppetState) state).videocraft$puppet();
		int extra = p == null ? -1 : p.tintColor();
		return extra == -1 ? tint : ARGB.multiply(tint, extra);
	}
}
