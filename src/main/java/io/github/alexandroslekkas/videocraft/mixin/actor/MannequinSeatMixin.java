package io.github.alexandroslekkas.videocraft.mixin.actor;

import io.github.alexandroslekkas.videocraft.actor.PuppetState;
import io.github.alexandroslekkas.videocraft.actor.Puppet;
import net.minecraft.client.renderer.entity.player.AvatarRenderer;
import net.minecraft.client.renderer.entity.state.AvatarRenderState;
import net.minecraft.world.entity.Avatar;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** A mannequin puppet in its {@code sit} state is drawn seated (legs forward), the way a riding player is. */
@Mixin(AvatarRenderer.class)
abstract class MannequinSeatMixin {
	@Inject(method = "extractRenderState(Lnet/minecraft/world/entity/Avatar;Lnet/minecraft/client/renderer/entity/state/AvatarRenderState;F)V", at = @At("TAIL"))
	private void videocraft$seat(Avatar avatar, AvatarRenderState state, float partialTicks, CallbackInfo info) {
		Puppet p = ((PuppetState) state).videocraft$puppet();
		if (p == null) return;
		if (p.has("sit")) { state.isPassenger = true; state.isCrouching = false; }
		state.nameTag = null;
	}
}
