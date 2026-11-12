package io.github.alexandroslekkas.videocraft.mixin;

import net.minecraft.client.DeltaTracker;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** The fraction of a tick the game clock carries over, so a shot can start on a tick boundary (Film.rebase). */
@Mixin(DeltaTracker.Timer.class)
public interface TimerAccessor {
	@Accessor("deltaTickResidual")
	void videocraft$residual(float residual);
}
