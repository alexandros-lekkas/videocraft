package dev.blockreel.api;

/**
 * How another mod adds its own staging actions and camera rigs without blockreel depending on it. List the class
 * under the {@code "blockreel"} entrypoint in that mod's {@code fabric.mod.json}:
 * <pre>{@code "entrypoints": { "blockreel": ["com.example.MyShots"] }}</pre>
 * It is only loaded when blockreel is present and a take is running, so the other mod can keep blockreel a
 * dev-only dependency ({@code modCompileOnly} / {@code modLocalRuntime}). Ids must be namespaced with the mod's id
 * ({@code t3craft:open_card}); bare ids belong to blockreel itself.
 */
@FunctionalInterface
public interface BlockreelPlugin {
	void register(Registry registry);
}
