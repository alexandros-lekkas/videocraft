package dev.blockreel;

import org.objectweb.asm.tree.ClassNode;
import org.spongepowered.asm.mixin.extensibility.IMixinConfigPlugin;
import org.spongepowered.asm.mixin.extensibility.IMixinInfo;

import java.util.List;
import java.util.Set;

/**
 * {@code -Dblockreel.hidden=true}: the client never shows its window, never takes focus and (on macOS) never gets a
 * Dock icon. The game still renders into its own framebuffer, so captured frames are real. Gates
 * {@code blockreel.dev.mixins.json}: without the property none of those mixins is even loaded.
 * Ported from T3 Craft's HiddenWindow (MIT, same owner).
 */
public final class HiddenWindow implements IMixinConfigPlugin {
	public static final boolean ENABLED = Boolean.getBoolean("blockreel.hidden");
	/** {@code SDL_WINDOW_HIDDEN}: the window is created but never mapped. Minecraft 26.3 windows through SDL3, not GLFW. */
	public static final long SDL_WINDOW_HIDDEN = 0x8L;

	public static void announce() {
		BlockreelLog.LOGGER.info("BLOCKREEL hidden client (-Dblockreel.hidden=true): no window, no Dock icon, no focus; frames still render. -Pshow=true shows it.");
	}

	@Override public void onLoad(String mixinPackage) {}
	@Override public String getRefMapperConfig() { return null; }
	@Override public boolean shouldApplyMixin(String targetClassName, String mixinClassName) { return ENABLED; }
	@Override public void acceptTargets(Set<String> myTargets, Set<String> otherTargets) {}
	@Override public List<String> getMixins() { return null; }
	@Override public void preApply(String targetClassName, ClassNode targetClass, String mixinClassName, IMixinInfo mixinInfo) {}
	@Override public void postApply(String targetClassName, ClassNode targetClass, String mixinClassName, IMixinInfo mixinInfo) {}
}
