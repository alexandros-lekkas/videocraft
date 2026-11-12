package io.github.alexandroslekkas.videocraft.text;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import io.github.alexandroslekkas.videocraft.director.Take;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Map;
import java.util.WeakHashMap;

/**
 * {@code shots/<name>/text.json}: every text item of a recorded shot, for measure and lint (DESIGN.md section 5). Rewritten
 * each time an item leaves the screen, so it is complete when the shot ends. Boxes are frame pixels {@code [x0, y0, x1,
 * y1]} (x1, y1 exclusive) at rest size (not mid-pop); frames are frames of the shot's video, inclusive.
 */
final class TextLog {
	/** Per shot run (identity): a warm client playing the same plan again starts a fresh file. */
	private static final Map<ShotContext, JsonArray> ITEMS = new WeakHashMap<>();

	private TextLog() {}

	static void add(ShotContext shot, JsonObject record) {
		// Staging and pre-roll are never recorded: an item never drawn on a recorded frame is not in the file.
		if (record.get("first_frame").isJsonNull()) return;
		JsonArray items = ITEMS.computeIfAbsent(shot, k -> new JsonArray());
		record.addProperty("id", items.size());
		items.add(record);
		write(shot, items);
	}

	private static void write(ShotContext shot, JsonArray items) {
		Take take = Take.fromSystemProperty();
		if (take == null) return;
		TextLayout layout = Ink.layout();
		JsonObject o = new JsonObject();
		o.addProperty("shot", shot.shot());
		o.addProperty("fps", shot.fps());
		o.addProperty("width", layout.frameWidth());
		o.addProperty("height", layout.frameHeight());
		o.addProperty("layout_scale", layout.scale());
		o.add("safe", Message.box(layout.safeFrame()));
		o.addProperty("min_cap_height", TextLayout.MIN_CAP * layout.scale());
		o.add("items", items);
		try {
			Files.writeString(take.shot(shot.shot()).resolve("text.json"), new GsonBuilder().setPrettyPrinting().serializeNulls().create().toJson(o) + "\n",
				StandardCharsets.UTF_8);
		} catch (IOException e) {
			VideocraftLog.LOGGER.warn("VIDEOCRAFT could not write text.json of {}", shot.shot(), e);
		}
	}
}
