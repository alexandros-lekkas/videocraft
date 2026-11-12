package dev.blockreel.devmixin;

import com.mojang.blaze3d.platform.Window;
import dev.blockreel.HiddenWindow;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.ModifyArg;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * Only with {@code -Dblockreel.hidden=true}: the SDL window is created hidden, and the game keeps believing it is
 * focused and not minimised, so it neither pauses nor drops to its background frame rate.
 */
@Mixin(Window.class)
abstract class HiddenWindowMixin {
	@ModifyArg(method = "createWindow", index = 3,
		at = @At(value = "INVOKE", target = "Lcom/mojang/renderpearl/api/device/GpuBackend;createWindow(Ljava/lang/String;IIJ)J"))
	private long blockreel$createHidden(long flags) {
		return flags | HiddenWindow.SDL_WINDOW_HIDDEN;
	}

	@Inject(method = {"onFocus", "onIconified"}, at = @At("HEAD"), cancellable = true)
	private void blockreel$keepActive(boolean value, CallbackInfo info) {
		info.cancel();
	}
}
