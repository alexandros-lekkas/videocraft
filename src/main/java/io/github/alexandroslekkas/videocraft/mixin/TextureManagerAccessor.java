package io.github.alexandroslekkas.videocraft.mixin;

import net.minecraft.client.renderer.texture.TextureManager;
import net.minecraft.client.renderer.texture.TickableTexture;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

import java.util.Set;

/** The animated textures (water, lava, fire, portals), so a shot can start them on their first frame (Film.rebase). */
@Mixin(TextureManager.class)
public interface TextureManagerAccessor {
	@Accessor("tickableTextures")
	Set<TickableTexture> videocraft$tickable();
}
