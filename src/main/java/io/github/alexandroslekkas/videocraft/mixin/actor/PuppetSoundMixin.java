package io.github.alexandroslekkas.videocraft.mixin.actor;

import io.github.alexandroslekkas.videocraft.actor.Puppets;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * A puppet's entity makes the sounds its puppet means (its own footsteps, its voice on cue) through the client's sound
 * system on the frame they happen, and no others: vanilla would play an entity's sounds from the server, which never
 * hears of a client-side entity, and its random ambient sounds would make takes differ.
 */
@Mixin(Entity.class)
abstract class PuppetSoundMixin {
	@Inject(method = "playSound(Lnet/minecraft/sounds/SoundEvent;FF)V", at = @At("HEAD"), cancellable = true)
	private void videocraft$puppetSound(SoundEvent sound, float volume, float pitch, CallbackInfo info) {
		if (Puppets.sound((Entity) (Object) this, sound, volume, pitch)) info.cancel();
	}
}
