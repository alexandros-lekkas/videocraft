package io.github.alexandroslekkas.videocraft.api;

/**
 * How another mod adds its own staging actions and camera rigs without videocraft depending on it. List the class
 * under the {@code "videocraft"} entrypoint in that mod's {@code fabric.mod.json}:
 * <pre>{@code "entrypoints": { "videocraft": ["com.example.MyShots"] }}</pre>
 * It is only loaded when videocraft is present and a take is running, so the other mod can keep videocraft a
 * dev-only dependency ({@code modCompileOnly} / {@code modLocalRuntime}). Ids must be namespaced with the mod's id
 * ({@code t3craft:open_card}); bare ids belong to videocraft itself.
 */
@FunctionalInterface
public interface VideocraftPlugin {
	void register(Registry registry);
}
