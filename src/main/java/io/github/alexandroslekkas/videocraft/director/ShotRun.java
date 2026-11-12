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
	static final int PREPARE_FRAMES = 60, PREPARE_MAX_FRAMES = 60 * 15, DRAWN_FRAMES = 30;

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
	private int prepared, frame, drawnFor, lastVisible = -1;
	private boolean rebuilt;
	private boolean finished;
	private int poseFrame = -1;
	private Pose pose;
	private double lens = 70;

	private final long seed;

	ShotRun(Director director, String name, double duration, double preroll, List<Plan.Cue> timeline, boolean records, long seed) {
		this.seed = seed;
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

	long seed() { return seed; }

	boolean finished() { return finished; }

	/** Once per game frame, after the capture of the last one. */
	void advance() {
		if (finished) return;
		if (phase == Phase.PREPARE) {
			if (records) {
				prepared++;
				// Drawn means: every chunk in reach has arrived and nothing has been left to compile for half a second
				// (a section that has just arrived is only queued on a later frame, so one quiet frame is not enough).
				int visible = minecraft().levelRenderer.visibleSections().size();
				boolean quiet = minecraft().levelRenderer.hasRenderedAllSections() && chunksAround() && weatherSettled() && visible == lastVisible;
				lastVisible = visible;
				drawnFor = quiet ? drawnFor + 1 : 0;
				boolean drawn = drawnFor >= DRAWN_FRAMES;
				if (drawn && !rebuilt) {
					// Sections whose chunk was not ready when the section graph was last built wait in a side list that
					// is not always looked at again: rebuild the graph once from what is loaded now, then settle again.
					rebuilt = true;
					drawnFor = 0;
					drawn = false;
					minecraft().levelRenderer.sectionOcclusionGraph().invalidate();
				}
				if (prepared < PREPARE_FRAMES || (!drawn && prepared < PREPARE_MAX_FRAMES)) return;
				if (!drawn) VideocraftLog.LOGGER.warn("VIDEOCRAFT {} records before every section in view is drawn", name);
			}
			// Pre-roll: the timeline and the rig run from -preroll, unrecorded, so frame 0 starts mid-action.
			phase = Phase.ROLL;
			frame = -prerollFrames;
			if (records) director.rebase(this);
		} else {
			frame++;
		}
		if (phase == Phase.ROLL && frame >= 0) {
			phase = Phase.RECORD;
			if (records) director.beginSegment(this);
			if (records) VideocraftLog.LOGGER.info("VIDEOCRAFT film {} frame 0 after {} frames, {} sections; {}", name, prepared, lastVisible, Film.state(minecraft()));
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

	/** Whether the client's rain and thunder have reached the shot's weather (the sky and fog follow them). */
	private boolean weatherSettled() {
		var level = minecraft().level;
		if (level == null) return false;
		String w = director.shotWeather();
		float rain = w.equals("clear") ? 0 : 1, thunder = w.equals("thunder") ? 1 : 0;
		return Math.abs(level.getRainLevel(1) - rain) < 1e-4 && Math.abs(level.getThunderLevel(1) - thunder) < 1e-4;
	}

	/**
	 * Whether every chunk within render distance of the camera has reached the client. The server sends chunks a few
	 * at a time, and "all sections drawn" only covers those that have arrived: without this, two takes of one plan
	 * differed in which far hills were there.
	 */
	private boolean chunksAround() {
		var mc = minecraft();
		if (mc.level == null) return false;
		var at = mc.gameRenderer.mainCamera().position();
		int cx = (int) Math.floor(at.x) >> 4, cz = (int) Math.floor(at.z) >> 4, r = mc.options.getEffectiveRenderDistance();
		// Exactly the chunks the server sends a player there (ChunkTrackingView.isWithinDistance with neighbours), so
		// the outermost ring is there in every take, not only in the ones where it happened to arrive in time.
		for (int dx = -r - 2; dx <= r + 2; dx++)
			for (int dz = -r - 2; dz <= r + 2; dz++) {
				long x = Math.max(0, Math.abs(dx) - 2), z = Math.max(0, Math.abs(dz) - 2);
				if (x * x + z * z < (long) r * r && !mc.level.hasChunk(cx + dx, cz + dz)) return false;
			}
		return true;
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
		if (records) Film.cut();
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
