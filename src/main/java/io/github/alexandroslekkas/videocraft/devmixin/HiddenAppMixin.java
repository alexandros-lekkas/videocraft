package io.github.alexandroslekkas.videocraft.devmixin;

import com.mojang.blaze3d.systems.RenderSystem;
import io.github.alexandroslekkas.videocraft.HiddenWindow;
import org.lwjgl.sdl.SDLHints;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Only with {@code -Dvideocraft.hidden=true}. On macOS SDL otherwise turns the process into a foreground app when video
 * starts (Dock icon, menu bar, stolen focus) even with a hidden window. The hint must be set before {@code SDL_Init}.
 */
@Mixin(RenderSystem.class)
abstract class HiddenAppMixin {
	@Inject(method = "initBackendSystem", at = @At(value = "INVOKE", target = "Lorg/lwjgl/sdl/SDLInit;SDL_Init(I)Z"))
	private static void videocraft$stayInBackground(CallbackInfoReturnable<?> info) {
		SDLHints.SDL_SetHint("SDL_MAC_BACKGROUND_APP", "1");
		HiddenWindow.announce();
	}
}
