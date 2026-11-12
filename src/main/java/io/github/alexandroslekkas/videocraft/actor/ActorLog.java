package io.github.alexandroslekkas.videocraft.actor;

import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import io.github.alexandroslekkas.videocraft.director.Take;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/**
 * {@code shots/<name>/actors.csv}: one row per recorded frame per puppet, where it is drawn that frame. Measure and the
 * determinism check read it, so the columns are a contract (add at the end, never rename):
 * {@code frame,actor,x,y,z,yaw,head_yaw,head_pitch,state}. {@code yaw} is the body's heading, {@code head_yaw} the
 * head's world yaw, {@code head_pitch} positive looking down, {@code state} the gait or idle plus scripted states.
 */
final class ActorLog {
	static final String HEADER = "frame,actor,x,y,z,yaw,head_yaw,head_pitch,state\n";
	private static final Map<String, StringBuilder> SHOTS = new LinkedHashMap<>();
	private static final Map<String, Integer> LAST = new LinkedHashMap<>();

	private ActorLog() {}

	static void row(ShotContext shot, Puppet p) {
		String key = shot.shot() + "\u0000" + p.id;
		int frame = shot.frame();
		Integer last = LAST.get(key);
		if (last != null && frame <= last) return;
		LAST.put(key, frame);
		var feet = p.ground();
		double y = p.feetY();
		SHOTS.computeIfAbsent(shot.shot(), k -> new StringBuilder(HEADER)).append(String.format(Locale.ROOT, "%d,%s,%.4f,%.4f,%.4f,%.3f,%.3f,%.3f,%s%n",
			frame, p.id, feet.x, y, feet.z, Path.wrap(p.heading()), Path.wrap(p.headYaw()), p.headPitch(), p.stateLabel()));
	}

	/** Writes the shot's file once its rows are in (each puppet's cut calls this; the last call has every row). */
	static void write(ShotContext shot) {
		StringBuilder rows = SHOTS.get(shot.shot());
		if (rows == null) return;
		Take take = Take.fromSystemProperty();
		if (take == null) return;
		try {
			Files.writeString(take.shot(shot.shot()).resolve("actors.csv"), rows, StandardCharsets.UTF_8);
		} catch (IOException e) {
			VideocraftLog.LOGGER.warn("VIDEOCRAFT could not write actors.csv of {}", shot.shot(), e);
		}
	}
}
