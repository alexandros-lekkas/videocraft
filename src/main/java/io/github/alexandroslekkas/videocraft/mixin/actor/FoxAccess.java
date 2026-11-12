package io.github.alexandroslekkas.videocraft.mixin.actor;

import net.minecraft.world.entity.animal.fox.Fox;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/** A fox's own sleeping and faceplant poses, which vanilla only sets from its AI. */
@Mixin(Fox.class)
public interface FoxAccess {
	@Invoker("setSleeping") void videocraft$setSleeping(boolean value);

	@Invoker("setFaceplanted") void videocraft$setFaceplanted(boolean value);
}
