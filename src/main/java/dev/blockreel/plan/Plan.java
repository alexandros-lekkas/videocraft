package dev.blockreel.plan;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import dev.blockreel.api.Params;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

/**
 * plan.json: the compiled shot script the mod plays. The CLI writes it (cli/blockreel/script.py) from the authored
 * TOML with every default filled in, so the mod reads one canonical shape and never guesses. The format is
 * docs/SCRIPT.md; a change here is a change there and in script.py, in the same commit.
 */
public record Plan(int version, String name, long seed, Output output, World world, List<ActorSpec> actors, List<Shot> shots) {
	public static final int VERSION = 1;

	/** The captured frame. Width and height are framebuffer pixels. */
	public record Output(int width, int height, int fps) {}

	/**
	 * The world a take plays in: a new one from {@code seed} or a copy of a saved one ({@code save}, a folder name under
	 * the game's saves/), then staged with {@code stage} cues (run before the first shot, never recorded).
	 */
	public record World(String seed, String save, String gamemode, long time, String weather, double settle, List<Cue> stage, Params params) {}

	/** Someone in the scene besides the player's default self: {@code kind} is "player" or an NPC kind (docs/SCRIPT.md). */
	public record ActorSpec(String id, String kind, Params params) {}

	/** One shot: a rig, a length, and what happens when. */
	public record Shot(String name, double duration, Params camera, List<Cue> timeline, Params params) {}

	/** One timeline entry: at {@code at} seconds into the shot, start action {@code action} (for {@code actor}). */
	public record Cue(double at, String action, String actor, Params params) {}

	public static Plan read(Path file) throws IOException {
		return parse(JsonParser.parseString(Files.readString(file, StandardCharsets.UTF_8)).getAsJsonObject());
	}

	public static Plan parse(JsonObject root) {
		int version = root.get("version").getAsInt();
		if (version != VERSION) throw new IllegalArgumentException("plan.json version " + version + "; this mod reads version " + VERSION + " (rebuild the mod or the CLI)");
		JsonObject out = root.getAsJsonObject("output");
		Output output = new Output(out.get("width").getAsInt(), out.get("height").getAsInt(), out.get("fps").getAsInt());
		JsonObject w = root.getAsJsonObject("world");
		World world = new World(text(w, "seed"), text(w, "save"), w.get("gamemode").getAsString(), w.get("time").getAsLong(),
			w.get("weather").getAsString(), w.get("settle").getAsDouble(), cues(w.getAsJsonArray("stage"), "world.stage"), new Params(w, "world"));
		List<ActorSpec> actors = new ArrayList<>();
		for (JsonElement e : root.getAsJsonArray("actors")) {
			JsonObject a = e.getAsJsonObject();
			actors.add(new ActorSpec(a.get("id").getAsString(), a.get("kind").getAsString(), new Params(a, "actors." + a.get("id").getAsString())));
		}
		List<Shot> shots = new ArrayList<>();
		for (JsonElement e : root.getAsJsonArray("shots")) {
			JsonObject s = e.getAsJsonObject();
			String name = s.get("name").getAsString();
			shots.add(new Shot(name, s.get("duration").getAsDouble(), new Params(s.getAsJsonObject("camera"), "shots." + name + ".camera"),
				cues(s.getAsJsonArray("timeline"), "shots." + name + ".timeline"), new Params(s, "shots." + name)));
		}
		if (shots.isEmpty()) throw new IllegalArgumentException("plan.json has no shots");
		return new Plan(version, root.get("name").getAsString(), root.get("seed").getAsLong(), output, world, actors, shots);
	}

	private static List<Cue> cues(JsonArray array, String where) {
		List<Cue> cues = new ArrayList<>();
		if (array == null) return cues;
		int i = 0;
		for (JsonElement e : array) {
			JsonObject c = e.getAsJsonObject();
			cues.add(new Cue(c.get("at").getAsDouble(), c.get("do").getAsString(), c.has("actor") ? c.get("actor").getAsString() : "player",
				new Params(c, where + "[" + i++ + "]")));
		}
		return cues;
	}

	private static String text(JsonObject o, String key) {
		return o.has(key) && !o.get(key).isJsonNull() ? o.get(key).getAsString() : null;
	}
}
