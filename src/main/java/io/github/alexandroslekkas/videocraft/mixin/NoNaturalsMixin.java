package io.github.alexandroslekkas.videocraft.mixin;

import io.github.alexandroslekkas.videocraft.director.Director;
import net.minecraft.core.BlockPos;
import net.minecraft.util.RandomSource;
import net.minecraft.world.level.ChunkPos;
import net.minecraft.world.level.NaturalSpawner;
import net.minecraft.world.level.ServerLevelAccessor;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/**
 * During a take, new chunks are generated without their animals: the spawn_mobs gamerule stops spawning over time,
 * but not the herds that chunk generation places, and those wander through sets on their own. No take: nothing changes.
 */
@Mixin(NaturalSpawner.class)
abstract class NoNaturalsMixin {
	@Inject(method = "spawnMobsForChunkGeneration", at = @At("HEAD"), cancellable = true)
	private static void videocraft$noHerds(ServerLevelAccessor level, BlockPos center, ChunkPos chunk, RandomSource random, CallbackInfo info) {
		if (Director.current() != null) info.cancel();
	}
}
