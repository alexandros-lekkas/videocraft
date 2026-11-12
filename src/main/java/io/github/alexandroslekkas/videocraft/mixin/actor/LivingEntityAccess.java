package io.github.alexandroslekkas.videocraft.mixin.actor;

import net.minecraft.sounds.SoundEvent;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.entity.LivingEntity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/** The entity's own voice, for the {@code voice} action. */
@Mixin(LivingEntity.class)
public interface LivingEntityAccess {
	@Invoker("getHurtSound") SoundEvent videocraft$hurtSound(DamageSource source);

	@Invoker("getDeathSound") SoundEvent videocraft$deathSound();

	@Invoker("getSoundVolume") float videocraft$soundVolume();
}
