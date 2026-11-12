package io.github.alexandroslekkas.videocraft.mixin;

import io.github.alexandroslekkas.videocraft.director.Director;
import net.minecraft.client.Minecraft;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.ModifyArg;

/**
 * Once per rendered frame the director captures the last frame and returns the game time for this one: exactly
 * 1/fps seconds later while a take records, so the video is steady however long a frame takes. Real time otherwise.
 */
@Mixin(Minecraft.class)
abstract class ClockMixin {
	@ModifyArg(method = "runTick(Z)V", at = @At(value = "INVOKE", target = "Lnet/minecraft/client/DeltaTracker$Timer;advanceGameTime(J)I"))
	private long videocraft$clock(long realMs) {
		return Director.clock(realMs);
	}
}
