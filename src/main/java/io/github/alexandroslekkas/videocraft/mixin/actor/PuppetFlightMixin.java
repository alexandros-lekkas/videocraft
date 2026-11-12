package io.github.alexandroslekkas.videocraft.mixin.actor;

import com.mojang.blaze3d.vertex.PoseStack;
import com.mojang.math.Axis;
import io.github.alexandroslekkas.videocraft.actor.Puppet;
import io.github.alexandroslekkas.videocraft.actor.PuppetState;
import net.minecraft.client.renderer.entity.LivingEntityRenderer;
import net.minecraft.client.renderer.entity.state.LivingEntityRenderState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * A flying puppet's body banks into its turns and pitches with its climbs and dives ({@code actor.Flight}): after
 * vanilla has turned the model to its heading, it is rolled about its own forward axis and tilted about its side axis,
 * both through the middle of the body. Vanilla has no roll for any mob, so this is the only place it can go.
 */
@Mixin(LivingEntityRenderer.class)
abstract class PuppetFlightMixin {
	@Inject(method = "setupRotations", at = @At("TAIL"))
	private void videocraft$bank(LivingEntityRenderState state, PoseStack pose, float bodyRot, float scale, CallbackInfo info) {
		Puppet p = ((PuppetState) state).videocraft$puppet();
		if (p == null) return;
		float bank = p.bank(), pitch = p.airPitch();
		if (Math.abs(bank) < 1e-3f && Math.abs(pitch) < 1e-3f) return;
		float mid = state.boundingBoxHeight * 0.5f;
		pose.translate(0, mid, 0);
		// Here the model faces -Z with +X to its right: rolling about Z by -bank lowers the right side, tilting about X
		// by +pitch raises the nose.
		pose.rotateDegrees(Axis.ZP, -bank);
		pose.rotateDegrees(Axis.XP, pitch);
		pose.translate(0, -mid, 0);
	}
}
