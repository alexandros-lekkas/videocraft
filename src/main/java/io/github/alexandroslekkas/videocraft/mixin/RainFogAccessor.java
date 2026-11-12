package io.github.alexandroslekkas.videocraft.mixin;

import net.minecraft.client.renderer.fog.environment.AtmosphericFogEnvironment;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** How much rain thickens the fog, eased over time (Film.rebase). */
@Mixin(AtmosphericFogEnvironment.class)
public interface RainFogAccessor {
	@Accessor("rainFogMultiplier")
	void videocraft$rainFog(float multiplier);
}
