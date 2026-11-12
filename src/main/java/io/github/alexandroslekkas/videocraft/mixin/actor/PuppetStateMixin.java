package io.github.alexandroslekkas.videocraft.mixin.actor;

import io.github.alexandroslekkas.videocraft.actor.PuppetState;
import io.github.alexandroslekkas.videocraft.actor.Puppet;
import net.minecraft.client.renderer.entity.state.EntityRenderState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;

/** Render states are reused per entity; this one remembers which puppet (if any) it was last extracted from. */
@Mixin(EntityRenderState.class)
abstract class PuppetStateMixin implements PuppetState {
	@Unique private Puppet videocraft$puppet;

	@Override public Puppet videocraft$puppet() { return videocraft$puppet; }

	@Override public void videocraft$puppet(Puppet puppet) { videocraft$puppet = puppet; }
}
