package io.github.alexandroslekkas.videocraft.mixin.actor;

import net.minecraft.world.entity.item.ItemEntity;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Mutable;
import org.spongepowered.asm.mixin.gen.Accessor;

/** A dropped prop's bob and spin start from the take's seed, not from an unseeded random. */
@Mixin(ItemEntity.class)
public interface ItemEntityAccess {
	@Mutable @Accessor("bobOffs") void videocraft$setBobOffs(float value);
}
