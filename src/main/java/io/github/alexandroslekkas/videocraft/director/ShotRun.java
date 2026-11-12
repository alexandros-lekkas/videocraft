package io.github.alexandroslekkas.videocraft.director;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.api.Action;
import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.CameraRig;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.Pose;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import io.github.alexandroslekkas.videocraft.api.View;
import io.github.alexandroslekkas.videocraft.plan.Plan;
import net.minecraft.client.Minecraft;
import net.minecraft.world.phys.Vec3;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Random;

/**
 * One shot while it plays: prepared (rig made, view set, a short wait so teleports land), then recorded for exactly
 * {@code duration * fps} frames. Also used, unrecorded and without a rig, for the world's staging cues.
 *
 * <p>Frame alignment: {@link #advance()} runs at the start of a game frame, after the capture of the frame before.
 * While recording, {@code frame} is the index of the frame about to be rendered, so cues at {@code at} seconds
 * start on the first frame whose time is {@code >= at}, and row {@code n} of frames.csv is frame {@code n} of the video.
 */
final class ShotRun implements ShotContext {
	/**
	 * Frames a shot waits between being set up and recording: teleports and gamemode changes land, the world around a
	 * camera that has just moved is drawn, and fog and sky colours (which ease over game time) settle. At least the first
	 * number, then until every section in view is drawn, at most the second.
	 */
	static final int PREPARE_FRAMES = 60, PREPARE_MAX_FRAMES = 60 * 15;

	private record Running(Plan.Cue cue, Action action) {}

	private final Director director;
	final String name;
	private final double duration;
	private final List<Plan.Cue> due;
	private final List<Running> running = new ArrayList<>();
	private final boolean records;
	private final Random random;
	private final JsonArray marks = new JsonArray();
	private final FrameLog log = new FrameLog();
	private CameraRig rig;
	private int prepared, frame;
	private boolean recording, finished;
	private int poseFrame = -1;
	private Pose pose;

	ShotRun(Director director, String name, double duration, List<Plan.Cue> timeline, boolean records, long seed) {
		this.director = director;
		this.name = name;
		this.duration = duration;
		this.due = new ArrayList<>(timeline);
		this.due.sort(Comparator.comparingDouble(Plan.Cue::at));
		this.records = records;
		this.random = new Random(seed ^ name.hashCode());
	}

	void rig(CameraRig rig) { this.rig = rig; }

	CameraRig rig() { return rig; }

	boolean finished() { return finished; }

	/** Once per game frame, after the capture of the last one. */
	void advance() {
		if (finished) return;
		if (!recording) {
			if (records) {
				prepared++;
				boolean drawn = minecraft().levelRenderer.hasRenderedAllSections();
				if (prepared < PREPARE_FRAMES || (!drawn && prepared < PREPARE_MAX_FRAMES)) return;
				if (!drawn) VideocraftLog.LOGGER.warn("VIDEOCRAFT {} records before every section in view is drawn", name);
			}
			recording = true;
			frame = 0;
			if (records) director.beginSegment(this);
		} else {
			frame++;
			boolean over = records ? frame >= Math.round(duration * fps()) : due.isEmpty() && running.isEmpty();
			if (over) { finish(); return; }
		}
		for (Actor actor : director.actors()) actor.frame(this);
		while (!due.isEmpty() && due.getFirst().at() <= seconds() + 1e-9) {
			Plan.Cue cue = due.removeFirst();
			Action action = director.registries().action(cue.action()).create(cue.params(), this);
			VideocraftLog.LOGGER.info("VIDEOCRAFT {} {}s {}", name, String.format(java.util.Locale.ROOT, "%.3f", seconds()), cue.action());
			running.add(new Running(cue, action));
		}
		running.removeIf(r -> r.action().frame(this));
	}

	/** The camera for the frame being rendered; computed once per frame and logged while recording. */
	Pose pose(float partialTick) {
		if (rig == null) return null;
		int at = director.frames();
		if (at != poseFrame) {
			poseFrame = at;
			pose = rig.view() == View.FIRST ? null : rig.pose(this, partialTick);
			if (recording && records) logFrame();
		}
		return pose;
	}

	private void logFrame() {
		var p = minecraft().player;
		double[] player = p == null ? new double[5] : new double[] {p.getX(), p.getY(), p.getZ(), p.getYRot(), p.getXRot()};
		double[] cam = pose == null ? new double[] {player[0], p == null ? 0 : p.getEyeY(), player[2], player[3], player[4]}
			: new double[] {pose.x(), pose.y(), pose.z(), pose.yaw(), pose.pitch()};
		log.row(frame, seconds(), cam, rig.fov(), player, p != null && p.onGround());
	}

	/** Stops whatever is still running and writes frames.csv and marks.json. */
	void finish() {
		if (finished) return;
		finished = true;
		for (Running r : running) r.action().stop(this);
		running.clear();
		for (Actor actor : director.actors()) actor.cut(this);
		if (!records) return;
		director.endSegment();
		try {
			log.write(director.take().shot(name).resolve("frames.csv"));
			Files.writeString(director.take().shot(name).resolve("marks.json"), marks + "\n", StandardCharsets.UTF_8);
		} catch (IOException e) {
			VideocraftLog.LOGGER.warn("VIDEOCRAFT could not write the logs of {}", name, e);
		}
	}

	// ---- ShotContext ----

	@Override public Minecraft minecraft() { return Minecraft.getInstance(); }
	@Override public String shot() { return name; }
	@Override public int frame() { return recording ? frame : 0; }
	@Override public double seconds() { return frame() / (double) fps(); }
	@Override public double duration() { return duration; }
	@Override public boolean recording() { return recording && records; }
	@Override public int fps() { return director.plan().output().fps(); }
	@Override public Vec3 anchor(String name) { return director.anchor(name); }
	@Override public void anchor(String name, Vec3 at) { director.anchor(name, at); }
	@Override public Actor actor(String id) { return director.actor(id); }
	@Override public void command(String command) { director.command(command); }
	@Override public Random random() { return random; }
	@Override public Pose camera() {
		if (pose != null) return pose;
		var c = minecraft().gameRenderer.mainCamera();
		return new Pose(c.position().x, c.position().y, c.position().z, c.yRot(), c.xRot());
	}
	@Override public void fail(String reason) { director.fail(name + ": " + reason); }

	@Override
	public Vec3 position(Params params, String key) {
		JsonElement e = params.raw(key);
		if (e == null || e.isJsonNull()) throw new IllegalArgumentException(params.where() + ": missing position '" + key + "'");
		if (e.isJsonArray()) return vec(e.getAsJsonArray(), params.where() + "." + key);
		JsonObject o = e.getAsJsonObject();
		Vec3 base = anchor(o.get("anchor").getAsString());
		return o.has("offset") ? base.add(vec(o.getAsJsonArray("offset"), params.where() + "." + key + ".offset")) : base;
	}

	private static Vec3 vec(JsonArray a, String where) {
		if (a.size() != 3) throw new IllegalArgumentException(where + ": a position is [x, y, z]");
		return new Vec3(a.get(0).getAsDouble(), a.get(1).getAsDouble(), a.get(2).getAsDouble());
	}

	@Override
	public void mark(String label) {
		JsonObject m = new JsonObject();
		m.addProperty("label", label);
		m.addProperty("frame", frame());
		marks.add(m);
	}

	@Override
	public void mark(String label, double value) {
		JsonObject m = new JsonObject();
		m.addProperty("label", label);
		m.addProperty("frame", frame());
		m.addProperty("value", value);
		marks.add(m);
	}
}
