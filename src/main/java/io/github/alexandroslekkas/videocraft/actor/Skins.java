package io.github.alexandroslekkas.videocraft.actor;

import com.mojang.blaze3d.platform.NativeImage;
import io.github.alexandroslekkas.videocraft.api.Params;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.texture.DynamicTexture;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.resources.Identifier;

import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

/**
 * A mannequin's skin from a local PNG (64x64, as a player skin; the CLI makes the path absolute against the script),
 * uploaded as a texture of this mod and named in the mannequin's profile, so nothing is fetched from the network.
 * {@code model = "slim"} (three-pixel arms) or {@code "wide"}.
 */
final class Skins {
	private Skins() {}

	static CompoundTag profileTag(String actor, Params spec) {
		CompoundTag profile = new CompoundTag();
		String model = spec.string("model", "wide").toLowerCase(Locale.ROOT);
		if (!model.equals("wide") && !model.equals("slim")) throw new IllegalArgumentException(spec.where() + ": model is \"wide\" or \"slim\", not '" + model + "'");
		profile.putString("model", model);
		if (spec.has("skin")) {
			String name = "skins/" + actor.replaceAll("[^a-z0-9_-]", "_");
			upload(Path.of(spec.string("skin")), Identifier.fromNamespaceAndPath("videocraft", "textures/" + name + ".png"), spec.where() + ".skin");
			profile.putString("texture", "videocraft:" + name);
		}
		return profile;
	}

	private static void upload(Path file, Identifier id, String where) {
		if (!Files.isRegularFile(file)) throw new IllegalArgumentException(where + ": no skin PNG at " + file + " (paths are relative to the script)");
		NativeImage image;
		try (InputStream in = Files.newInputStream(file)) {
			image = NativeImage.read(in);
		} catch (IOException e) {
			throw new IllegalArgumentException(where + ": " + file + " is not a PNG: " + e.getMessage());
		}
		if (image.getWidth() != 64 || (image.getHeight() != 64 && image.getHeight() != 32)) {
			int w = image.getWidth(), h = image.getHeight();
			image.close();
			throw new IllegalArgumentException(where + ": a skin is 64x64 pixels, " + file + " is " + w + "x" + h);
		}
		Minecraft.getInstance().getTextureManager().register(id, new DynamicTexture(id::toString, image));
	}
}
