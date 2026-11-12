package io.github.alexandroslekkas.videocraft.mixin;

import io.github.alexandroslekkas.videocraft.director.Film;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.particle.Particle;
import net.minecraft.util.RandomSource;
import net.minecraft.world.entity.Entity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Redirect;

/**
 * The client's unseeded randoms (falling leaves, torch smoke, drips, each particle's drift, each new entity's) come
 * from the take's seed while a take runs, so two takes of one plan draw the same particles. No take: unchanged.
 */
@Mixin({ClientLevel.class, Particle.class, Entity.class})
abstract class FilmRandomMixin {
	@Redirect(method = {"animateTick", "<init>"}, at = @At(value = "INVOKE", target = "Lnet/minecraft/util/RandomSource;create()Lnet/minecraft/util/RandomSource;"), require = 0)
	private RandomSource videocraft$seeded() {
		return Film.random();
	}

	@Redirect(method = "animateTick", at = @At(value = "INVOKE", target = "Lnet/minecraft/util/RandomSource;createThreadLocalInstance()Lnet/minecraft/util/RandomSource;"), require = 0)
	private RandomSource videocraft$seededLocal() {
		return Film.random();
	}
}
