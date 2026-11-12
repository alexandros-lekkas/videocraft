package dev.blockreel.api;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;

import java.util.ArrayList;
import java.util.List;

/** The parameters of one cue or rig, as compiled into plan.json. Missing required keys throw with the key's name. */
public final class Params {
	private final JsonObject json;
	private final String where;

	public Params(JsonObject json, String where) {
		this.json = json == null ? new JsonObject() : json;
		this.where = where;
	}

	public JsonObject json() { return json; }

	/** Where these came from (shot and cue), for error messages. */
	public String where() { return where; }

	public boolean has(String key) { return json.has(key) && !json.get(key).isJsonNull(); }

	public String string(String key) { return require(key).getAsString(); }

	public String string(String key, String fallback) { return has(key) ? json.get(key).getAsString() : fallback; }

	public double number(String key) { return require(key).getAsDouble(); }

	public double number(String key, double fallback) { return has(key) ? json.get(key).getAsDouble() : fallback; }

	public boolean bool(String key, boolean fallback) { return has(key) ? json.get(key).getAsBoolean() : fallback; }

	public List<String> strings(String key) {
		List<String> out = new ArrayList<>();
		if (has(key)) for (JsonElement e : json.getAsJsonArray(key)) out.add(e.getAsString());
		return out;
	}

	public double[] numbers(String key) {
		JsonArray array = require(key).getAsJsonArray();
		double[] out = new double[array.size()];
		for (int i = 0; i < out.length; i++) out[i] = array.get(i).getAsDouble();
		return out;
	}

	public JsonElement raw(String key) { return json.get(key); }

	public Params child(String key) {
		return new Params(has(key) ? json.getAsJsonObject(key) : new JsonObject(), where + "." + key);
	}

	private JsonElement require(String key) {
		if (!has(key)) throw new IllegalArgumentException(where + ": missing '" + key + "'");
		return json.get(key);
	}
}
