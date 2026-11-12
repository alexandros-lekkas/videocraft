package io.github.alexandroslekkas.videocraft.mixin.sound;

import io.github.alexandroslekkas.videocraft.sound.SoundLog;
import net.minecraft.client.resources.sounds.AbstractSoundInstance;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundEngine;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * Makes the sound log deterministic: while a filmed shot runs, a sound about to start gets a random source seeded from
 * the take (SoundLog#random) before vanilla picks its variant and samples its volume and pitch with it. Vanilla seeds
 * most instances from the level's or an entity's unseeded random, so without this two takes would log different files.
 * Logging itself is a sound event listener (SoundLog), which vanilla calls before it drops zero-volume sounds.
 */
@Mixin(SoundEngine.class)
abstract class SoundEngineMixin {
	@Inject(method = "play", at = @At("HEAD"))
	private void videocraft$seed(SoundInstance instance, CallbackInfoReturnable<SoundEngine.PlayResult> cir) {
		if (instance instanceof AbstractSoundInstance && SoundLog.active()) {
			SoundInstanceAccessor a = (SoundInstanceAccessor) instance;
			if (a.videocraft$sound() == null) a.videocraft$random(SoundLog.random(instance.getIdentifier()));
		}
	}
}
