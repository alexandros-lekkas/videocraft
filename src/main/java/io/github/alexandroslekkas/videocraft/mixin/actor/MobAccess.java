package io.github.alexandroslekkas.videocraft.mixin.actor;

import net.minecraft.sounds.SoundEvent;
import net.minecraft.world.entity.Mob;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/** A mob's own ambient sound (a goat's bleat, a screaming goat's scream), for the {@code voice} action. */
@Mixin(Mob.class)
public interface MobAccess {
	@Invoker("getAmbientSound") SoundEvent videocraft$ambientSound();
}
