package io.github.alexandroslekkas.videocraft.director;

import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.api.ActionType;
import io.github.alexandroslekkas.videocraft.api.VideocraftPlugin;
import io.github.alexandroslekkas.videocraft.api.Registry;
import io.github.alexandroslekkas.videocraft.api.RigType;
import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.loader.api.entrypoint.EntrypointContainer;

import java.util.Map;
import java.util.TreeMap;

/**
 * Every action and rig a script can name: videocraft's own (registered by each workstream's {@code register} method)
 * and those of other mods' {@code "videocraft"} entrypoints. Ids are {@code namespace:name}; a bare name means
 * {@code videocraft:name}.
 */
public final class Registries implements Registry {
	private final Map<String, ActionType> actions = new TreeMap<>();
	private final Map<String, RigType> rigs = new TreeMap<>();
	private String owner = "videocraft";

	public static String id(String name) { return name.contains(":") ? name : "videocraft:" + name; }

	@Override
	public void action(String id, ActionType type) {
		put(actions, id, type, "action");
	}

	@Override
	public void rig(String id, RigType type) {
		put(rigs, id, type, "rig");
	}

	private <T> void put(Map<String, T> map, String id, T value, String what) {
		String full = id(id);
		if (!owner.equals("videocraft") && full.startsWith("videocraft:")) throw new IllegalArgumentException(owner + " registered the " + what + " '" + id + "' without its own namespace");
		if (map.putIfAbsent(full, value) != null) throw new IllegalArgumentException("the " + what + " '" + full + "' is registered twice (last by " + owner + ")");
	}

	public ActionType action(String name) {
		ActionType type = actions.get(id(name));
		if (type == null) throw new IllegalArgumentException("no action '" + name + "'; known: " + String.join(", ", actions.keySet()));
		return type;
	}

	public RigType rig(String name) {
		RigType type = rigs.get(id(name));
		if (type == null) throw new IllegalArgumentException("no camera rig '" + name + "'; known: " + String.join(", ", rigs.keySet()));
		return type;
	}

	/** Built-ins first, then every installed mod that lists a {@code "videocraft"} entrypoint. */
	public static Registries load() {
		Registries r = new Registries();
		CoreActions.register(r);
		io.github.alexandroslekkas.videocraft.camera.Rigs.register(r);
		io.github.alexandroslekkas.videocraft.actor.Actions.register(r);
		io.github.alexandroslekkas.videocraft.text.TextActions.register(r);
		io.github.alexandroslekkas.videocraft.sound.SoundActions.register(r);
		for (EntrypointContainer<VideocraftPlugin> plugin : FabricLoader.getInstance().getEntrypointContainers("videocraft", VideocraftPlugin.class)) {
			r.owner = plugin.getProvider().getMetadata().getId();
			plugin.getEntrypoint().register(r);
			VideocraftLog.LOGGER.info("VIDEOCRAFT plugin {} registered", r.owner);
		}
		r.owner = "videocraft";
		VideocraftLog.LOGGER.info("VIDEOCRAFT actions {} rigs {}", r.actions.keySet(), r.rigs.keySet());
		return r;
	}
}
