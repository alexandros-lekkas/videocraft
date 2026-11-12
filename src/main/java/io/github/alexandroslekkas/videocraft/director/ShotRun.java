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
	/** Set up and waiting for the world to be drawn; running unrecorded from -preroll; recording from frame 0. */
	private enum Phase { PREPARE, ROLL, RECORD }

	private final int prerollFrames;
	private Phase phase = Phase.PREPARE;
	private int prepared, frame;
	private boolean finished;
	private int poseFrame = -1;
	private Pose pose;
	private double lens = 70;

	ShotRun(Director director, String name, double duration, double preroll, List<Plan.Cue> timeline, boolean records, long seed) {
		this.director = director;
		this.prerollFrames = (int) Math.round(Math.max(0, preroll) * director.plan().output().fps());
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
		if (phase == Phase.PREPARE) {
			if (records) {
				prepared++;
				boolean drawn = minecraft().levelRenderer.hasRenderedAllSections();
				if (prepared < PREPARE_FRAMES || (!drawn && prepared < PREPARE_MAX_FRAMES)) return;
				if (!drawn) VideocraftLog.LOGGER.warn("VIDEOCRAFT {} records before every section in view is drawn", name);
			}
			// Pre-roll: the timeline and the rig run from -preroll, unrecorded, so frame 0 starts mid-action.
			phase = Phase.ROLL;
			frame = -prerollFrames;
		} else {
			frame++;
		}
		if (phase == Phase.ROLL && frame >= 0) {
			phase = Phase.RECORD;
			if (records) director.beginSegment(this);
		} else if (phase == Phase.RECORD) {
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
			lens = rig.fov(this);
			if (recording()) logFrame();
		}
		return pose;
	}

	private void logFrame() {
		var p = minecraft().player;
		double[] player = p == null ? new double[5] : new double[] {p.getX(), p.getY(), p.getZ(), p.getYRot(), p.getXRot()};
		double[] cam = pose == null ? new double[] {player[0], p == null ? 0 : p.getEyeY(), player[2], player[3], player[4]}
			: new double[] {pose.x(), pose.y(), pose.z(), pose.yaw(), pose.pitch()};
		String subjectId = rig.subject();
		double[] subject = null;
		if (subjectId != null) {
			try {
				Actor a = director.actor(subjectId);
				Vec3 g = a.ground();
				subject = new double[] {g.x, g.y, g.z, a.heading(), a.head().y};
			} catch (RuntimeException e) {
				subject = null;
			}
		}
		log.row(frame, seconds(), cam, lens, player, p != null && p.onGround(), subjectId, subject);
	}

	/** The field of view of the frame being rendered (see {@link CameraRig#fov(ShotContext)}). */
	double lens() { return lens; }

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
	/** Negative during pre-roll, {@code -preroll * fps} while the shot is prepared. */
	@Override public int frame() { return phase == Phase.PREPARE ? -prerollFrames : frame; }
	@Override public double seconds() { return frame() / (double) fps(); }
	@Override public double duration() { return duration; }
	@Override public boolean recording() { return phase == Phase.RECORD && records; }
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
		if (!e.isJsonObject()) throw new IllegalArgumentException(params.where() + "." + key + ": a position is [x, y, z], {anchor = \"name\"} or {actor = \"id\"}");
		JsonObject o = e.getAsJsonObject();
		Vec3 base;
		if (o.has("actor")) {
			// On an actor, where it stands now: offset in world axes, or front/right/up along the way it faces.
			Actor a = actor(o.get("actor").getAsString());
			base = a.ground();
			double yaw = Math.toRadians(a.heading());
			Vec3 front = new Vec3(-Math.sin(yaw), 0, Math.cos(yaw)), right = new Vec3(-Math.cos(yaw), 0, -Math.sin(yaw));
			if (o.has("front")) base = base.add(front.scale(o.get("front").getAsDouble()));
			if (o.has("right")) base = base.add(right.scale(o.get("right").getAsDouble()));
			if (o.has("up")) base = base.add(0, o.get("up").getAsDouble(), 0);
		} else if (o.has("anchor")) {
			base = anchor(o.get("anchor").getAsString());
		} else {
			throw new IllegalArgumentException(params.where() + "." + key + ": a position table names an anchor or an actor");
		}
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
