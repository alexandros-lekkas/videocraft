package io.github.alexandroslekkas.videocraft.actor;

import net.minecraft.client.Minecraft;
import net.minecraft.sounds.SoundEvent;
import net.minecraft.world.entity.Entity;

import java.util.IdentityHashMap;
import java.util.Map;

/**
 * The entities the puppets own, for the actor mixins: which ones the level must not tick, at which fraction of a tick
 * each is drawn, which sounds they may make and how their models are tinted. Render thread only.
 */
public final class Puppets {
	private static final Map<Entity, Puppet> OWNED = new IdentityHashMap<>();
	/** True while a puppet runs its entity's tick (the level's own ticking of it is skipped). */
	static boolean ticking;
	/** True while a puppet means to make a sound (footsteps, its voice): everything else it would play is silent. */
	static boolean voicing;

	private Puppets() {}

	static void own(Entity e, Puppet p) { OWNED.put(e, p); }

	static void disown(Entity e) { if (e != null) OWNED.remove(e); }

	static void clear() { OWNED.clear(); }

	public static Puppet of(Entity e) { return OWNED.isEmpty() ? null : OWNED.get(e); }

	/** Whether the level should skip its own tick of {@code e}: a puppet's entity, outside the puppet's own tick. */
	public static boolean frozen(Entity e) { return !ticking && of(e) != null; }

	/** The fraction of a tick to draw {@code e} at: the puppet's own (from the frame clock), else the game's. */
	public static float partial(Entity e, float game) {
		Puppet p = of(e);
		return p == null ? game : p.phase();
	}

	/**
	 * A sound a puppet's entity asks for: played on the client's sound system when the puppet means it (vanilla would
	 * send it from the server, which does not know a client-side entity), silent otherwise. True: handled.
	 */
	public static boolean sound(Entity e, SoundEvent sound, float volume, float pitch) {
		Puppet p = of(e);
		if (p == null) return false;
		if (voicing && !e.isSilent()) {
			var level = Minecraft.getInstance().level;
			if (level != null) level.playLocalSound(e.getX(), e.getY(), e.getZ(), sound, e.getSoundSource(), volume, pitch, false);
			p.heard(sound);
		}
		return true;
	}

	/** The model tint for {@code e} (ARGB, multiplied in), or -1. */
	public static int tint(Entity e) {
		Puppet p = of(e);
		return p == null ? -1 : p.tintColor();
	}
}
