package io.github.alexandroslekkas.videocraft.mixin.actor;

import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.block.state.BlockState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
import org.spongepowered.asm.mixin.gen.Invoker;

/** A puppet counts its own footsteps the way vanilla does and plays the entity's own step sound. */
@Mixin(Entity.class)
public interface EntityAccess {
	@Accessor("nextStep") float videocraft$nextStep();

	@Accessor("nextStep") void videocraft$setNextStep(float value);

	@Invoker("nextStep") float videocraft$computeNextStep();

	@Invoker("playStepSound") void videocraft$playStepSound(BlockPos pos, BlockState state);
}
