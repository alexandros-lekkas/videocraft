package io.github.alexandroslekkas.videocraft.mixin;

import net.minecraft.client.renderer.fog.FogRenderer;
import net.minecraft.client.renderer.fog.environment.FogEnvironment;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.List;

/** The fog environments, whose rain fog eases over time (Film.rebase). */
@Mixin(FogRenderer.class)
public interface FogAccessor {
	@Accessor("FOG_ENVIRONMENTS")
	static List<FogEnvironment> videocraft$environments() { throw new AssertionError(); }
}
