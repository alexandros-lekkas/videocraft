package io.github.alexandroslekkas.videocraft.mixin;

import net.minecraft.client.renderer.texture.SpriteContents;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** Where an animated sprite is in its loop (Film.rebase). */
@Mixin(SpriteContents.AnimationState.class)
public interface AnimationStateAccessor {
	@Accessor("frame")
	void videocraft$frame(int frame);

	@Accessor("subFrame")
	void videocraft$subFrame(int subFrame);

	@Accessor("isDirty")
	void videocraft$dirty(boolean dirty);
}
