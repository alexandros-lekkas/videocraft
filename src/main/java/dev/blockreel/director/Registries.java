package dev.blockreel.director;

import dev.blockreel.BlockreelLog;
import dev.blockreel.api.ActionType;
import dev.blockreel.api.BlockreelPlugin;
import dev.blockreel.api.Registry;
import dev.blockreel.api.RigType;
import net.fabricmc.loader.api.FabricLoader;
import net.fabricmc.loader.api.entrypoint.EntrypointContainer;

import java.util.Map;
import java.util.TreeMap;

/**
 * Every action and rig a script can name: blockreel's own (registered by each workstream's {@code register} method)
 * and those of other mods' {@code "blockreel"} entrypoints. Ids are {@code namespace:name}; a bare name means
 * {@code blockreel:name}.
 */
public final class Registries implements Registry {
	private final Map<String, ActionType> actions = new TreeMap<>();
	private final Map<String, RigType> rigs = new TreeMap<>();
	private String owner = "blockreel";

	public static String id(String name) { return name.contains(":") ? name : "blockreel:" + name; }

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
		if (!owner.equals("blockreel") && full.startsWith("blockreel:")) throw new IllegalArgumentException(owner + " registered the " + what + " '" + id + "' without its own namespace");
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

	/** Built-ins first, then every installed mod that lists a {@code "blockreel"} entrypoint. */
	public static Registries load() {
		Registries r = new Registries();
		CoreActions.register(r);
		dev.blockreel.camera.Rigs.register(r);
		dev.blockreel.actor.Actions.register(r);
		dev.blockreel.text.TextActions.register(r);
		for (EntrypointContainer<BlockreelPlugin> plugin : FabricLoader.getInstance().getEntrypointContainers("blockreel", BlockreelPlugin.class)) {
			r.owner = plugin.getProvider().getMetadata().getId();
			plugin.getEntrypoint().register(r);
			BlockreelLog.LOGGER.info("BLOCKREEL plugin {} registered", r.owner);
		}
		r.owner = "blockreel";
		BlockreelLog.LOGGER.info("BLOCKREEL actions {} rigs {}", r.actions.keySet(), r.rigs.keySet());
		return r;
	}
}
