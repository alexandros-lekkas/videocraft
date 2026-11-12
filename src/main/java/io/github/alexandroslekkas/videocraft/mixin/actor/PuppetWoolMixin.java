package io.github.alexandroslekkas.videocraft.mixin.actor;

import io.github.alexandroslekkas.videocraft.actor.Puppet;
import io.github.alexandroslekkas.videocraft.actor.PuppetState;
import net.minecraft.client.renderer.entity.state.SheepRenderState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/** {@code wool = "#rrggbb"}: a sheep puppet's wool layer takes any colour, not only one of the sixteen dyes. */
@Mixin(SheepRenderState.class)
abstract class PuppetWoolMixin {
	@Inject(method = "getWoolColor", at = @At("HEAD"), cancellable = true)
	private void videocraft$wool(CallbackInfoReturnable<Integer> cir) {
		Puppet p = ((PuppetState) this).videocraft$puppet();
		if (p != null && p.woolColor() != -1) cir.setReturnValue(p.woolColor());
	}
}
