package io.github.alexandroslekkas.videocraft.mixin;

import io.github.alexandroslekkas.videocraft.director.Film;
import net.minecraft.client.multiplayer.ClientLevel;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * While a shot runs, the client's game time (what clouds, beacon beams and other time-driven pictures read) counts
 * the shot's own ticks instead of the server's, which depend on how long the take took to get there. No take or
 * between shots: the game's own.
 */
@Mixin(ClientLevel.ClientLevelData.class)
abstract class FilmTimeMixin {
	@Inject(method = "getGameTime", at = @At("HEAD"), cancellable = true)
	private void videocraft$filmTime(CallbackInfoReturnable<Long> info) {
		long t = Film.gameTime();
		if (t >= 0) info.setReturnValue(t);
	}
}
