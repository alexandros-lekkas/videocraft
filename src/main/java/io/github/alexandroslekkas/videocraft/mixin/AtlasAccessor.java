package io.github.alexandroslekkas.videocraft.mixin;

import net.minecraft.client.renderer.texture.SpriteContents;
import net.minecraft.client.renderer.texture.TextureAtlas;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.List;

/** An atlas's animated sprites (Film.rebase). */
@Mixin(TextureAtlas.class)
public interface AtlasAccessor {
	@Accessor("animatedTexturesStates")
	List<SpriteContents.AnimationState> videocraft$animations();
}
