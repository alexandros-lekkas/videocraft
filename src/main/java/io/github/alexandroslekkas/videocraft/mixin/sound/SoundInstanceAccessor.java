package io.github.alexandroslekkas.videocraft.mixin.sound;

import net.minecraft.client.resources.sounds.AbstractSoundInstance;
import net.minecraft.client.resources.sounds.Sound;
import net.minecraft.util.RandomSource;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Mutable;
import org.spongepowered.asm.mixin.gen.Accessor;

/** Reaches a sound instance's variant (null until resolved) and its random source, for {@link SoundEngineMixin}. */
@Mixin(AbstractSoundInstance.class)
public interface SoundInstanceAccessor {
	@Accessor("sound")
	Sound videocraft$sound();

	@Mutable
	@Accessor("random")
	void videocraft$random(RandomSource random);
}
