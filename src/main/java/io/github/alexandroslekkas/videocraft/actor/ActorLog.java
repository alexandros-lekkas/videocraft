package io.github.alexandroslekkas.videocraft.actor;

import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import io.github.alexandroslekkas.videocraft.director.Take;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
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
	private static final Map<String, List<String>> SHOTS = new LinkedHashMap<>();
	private static final Map<String, Integer> LAST = new LinkedHashMap<>();
	/** Where each puppet's last row is in its shot's list, so a cue on the same frame can correct it. */
	private static final Map<String, Integer> AT = new LinkedHashMap<>();

	private ActorLog() {}

	static void row(ShotContext shot, Puppet p) {
		String key = shot.shot() + "\u0000" + p.id;
		int frame = shot.frame();
		Integer last = LAST.get(key);
		if (last != null && frame <= last) return;
		LAST.put(key, frame);
		List<String> rows = SHOTS.computeIfAbsent(shot.shot(), k -> new ArrayList<>());
		AT.put(key, rows.size());
		rows.add(line(frame, p));
	}

	/** Rewrites this frame's row of a puppet that a cue has just moved (a place after the tick that logged it). */
	static void amend(ShotContext shot, Puppet p) {
		String key = shot.shot() + "\u0000" + p.id;
		Integer last = LAST.get(key), at = AT.get(key);
		List<String> rows = SHOTS.get(shot.shot());
		if (last == null || at == null || rows == null || last != shot.frame()) return;
		rows.set(at, line(last, p));
	}

	private static String line(int frame, Puppet p) {
		var feet = p.ground();
		return String.format(Locale.ROOT, "%d,%s,%.4f,%.4f,%.4f,%.3f,%.3f,%.3f,%s%n",
			frame, p.id, feet.x, p.feetY(), feet.z, Path.wrap(p.heading()), Path.wrap(p.headYaw()), p.headPitch(), p.stateLabel());
	}

	/** Writes the shot's file once its rows are in (each puppet's cut calls this; the last call has every row). */
	static void write(ShotContext shot) {
		List<String> list = SHOTS.get(shot.shot());
		if (list == null) return;
		String rows = HEADER + String.join("", list);
		Take take = Take.fromSystemProperty();
		if (take == null) return;
		try {
			Files.writeString(take.shot(shot.shot()).resolve("actors.csv"), rows, StandardCharsets.UTF_8);
		} catch (IOException e) {
			VideocraftLog.LOGGER.warn("VIDEOCRAFT could not write actors.csv of {}", shot.shot(), e);
		}
	}
}
