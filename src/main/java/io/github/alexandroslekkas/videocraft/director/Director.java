package io.github.alexandroslekkas.videocraft.director;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.CameraRig;
import io.github.alexandroslekkas.videocraft.api.Pose;
import io.github.alexandroslekkas.videocraft.api.View;
import io.github.alexandroslekkas.videocraft.actor.Cast;
import io.github.alexandroslekkas.videocraft.plan.Plan;
import io.github.alexandroslekkas.videocraft.text.TextLayer;
import net.minecraft.client.CameraType;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.EntitySpawnReason;
import net.minecraft.world.entity.EntityTypes;
import net.minecraft.world.phys.Vec3;

import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Plays one take: title screen → world (new from a seed, or a saved one) → arrival → staging → shots → encoders
 * finished → result.json → quit. Game ticks drive the steps before the shots ({@link #tick}); once the first shot is
 * prepared, everything runs per rendered frame on the fixed clock ({@link #clock}). Any failure ends the take with
 * {@code VIDEOCRAFT RESULT FAIL <reason>}; nothing is cut from a broken take.
 */
public final class Director {
	private static volatile Director current;

	/** Called once per frame by ClockMixin: captures the last frame and returns this frame's game time. */
	public static long clock(long realMs) {
		Director d = current;
		return d == null ? realMs : d.frame(realMs);
	}

	/** Called once per rendered frame by CameraMixin: the rig's camera, or null to leave the game's. */
	public static Pose camera(float partialTick) {
		Director d = current;
		return d == null || d.shot == null || d.step != Step.SHOTS ? null : d.shot.pose(partialTick);
	}

	/** Whether vanilla HUD elements (hotbar, hearts, crosshair) draw this frame: only through the player's own eyes, if the shot asks. */
	public static boolean hudVisible() {
		Director d = current;
		return d == null || d.hud;
	}

	/** Whether the local player is hidden this frame: while an unseen operator holds the camera ({@link View#CAMERA}). */
	public static boolean hidesPlayer() {
		Director d = current;
		return d != null && d.shot != null && d.shot.rig() != null && d.shot.rig().view() == View.CAMERA;
	}

	enum Step { BOOT, WORLD, ARRIVE, SETTLE, STAGE, SHOTS, FINISH, DONE }

	private static final int BOOT_TICKS = 20 * 240;

	private final Take take;
	private final Plan plan;
	private final Registries registries;
	private final Capture capture;
	private final Map<String, Vec3> anchors = new HashMap<>();
	private Map<String, Actor> cast = Map.of();
	private Step step = Step.BOOT;
	private int ticks, stepTicks, shotIndex = -1, frames;
	private long stepNanos = System.nanoTime();
	private final long startNanos = System.nanoTime();
	private boolean fixed, hud = true;
	private double virtualMs = -1;
	private ShotRun shot;
	private Entity marker;
	private Vec3 parkedFrom;
	private String levelId, failure;
	private long recordNanos;
	private int recordedFrames;

	private Director(Take take, Plan plan, Registries registries) {
		this.take = take;
		this.plan = plan;
		this.registries = registries;
		this.capture = new Capture(System.getProperty("videocraft.ffmpeg", "ffmpeg"));
	}

	public static Director start(Take take, Plan plan, Registries registries) {
		Director d = new Director(take, plan, registries);
		current = d;
		Hud.install();
		TextLayer.install();
		VideocraftLog.LOGGER.info("VIDEOCRAFT take {} '{}': {} shots at {}x{} {} fps", take.dir(), plan.name(), plan.shots().size(), plan.output().width(), plan.output().height(), plan.output().fps());
		return d;
	}

	public static Director current() { return current; }

	// ---- Accessors for ShotRun and the control server ----

	Take take() { return take; }
	Plan plan() { return plan; }
	Registries registries() { return registries; }
	int frames() { return frames; }
	java.util.Collection<Actor> actors() { return cast.values(); }

	Actor actor(String id) {
		Actor a = cast.get(id);
		if (a == null) throw new IllegalArgumentException("no actor '" + id + "' in this take; staged: " + cast.keySet());
		return a;
	}

	void addActor(Actor actor) {
		if (cast.containsKey(actor.id())) throw new IllegalArgumentException("the actor '" + actor.id() + "' is staged twice");
		cast.put(actor.id(), actor);
	}

	Vec3 anchor(String name) {
		Vec3 at = anchors.get(name);
		if (at == null) throw new IllegalArgumentException("no anchor '" + name + "'; known: " + anchors.keySet());
		return at;
	}

	void anchor(String name, Vec3 at) { anchors.put(name, at); }

	synchronized JsonObject status() {
		JsonObject o = new JsonObject();
		o.addProperty("step", step.name());
		o.addProperty("shot", shot == null ? null : shot.name);
		o.addProperty("frame", shot == null ? 0 : shot.frame());
		o.addProperty("frames", frames);
		o.addProperty("seconds", (System.nanoTime() - startNanos) / 1e9);
		return o;
	}

	void command(String command) {
		var server = Minecraft.getInstance().getSingleplayerServer();
		if (server == null) throw new IllegalStateException("no integrated server for the command: " + command);
		Vec3 at = anchors.get("spawn");
		server.execute(() -> {
			String error = Commands.run(server, at, command);
			if (error != null) VideocraftLog.LOGGER.warn("VIDEOCRAFT command \"{}\" failed: {}", command, error);
		});
	}

	void fail(String reason) {
		if (failure == null) failure = reason;
	}

	// ---- Game ticks: everything before the shots ----

	public void tick(Minecraft mc) {
		if (step == Step.DONE) return;
		ticks++;
		stepTicks++;
		try {
			if (failure == null && capture.error() != null) failure = capture.error();
			if (failure != null) { finish(mc, false, failure); return; }
			if (step.ordinal() < Step.SHOTS.ordinal() && ticks > BOOT_TICKS) { finish(mc, false, "timed out at " + step); return; }
			switch (step) {
				case BOOT -> boot(mc);
				case WORLD -> { if (mc.level != null && mc.player != null) go(Step.ARRIVE); }
				case ARRIVE -> arrive(mc);
				case SETTLE -> settle(mc);
				case FINISH -> { if (capture.idle()) finish(mc, true, null); else if (stepTicks > 20 * 120) finish(mc, false, "encoders did not finish"); }
				default -> {}
			}
			// Command feedback and join messages never belong in a frame.
			if (mc.player != null) mc.gui.hud.getChat().clearMessages(false);
			if (marker != null && shot != null && shot.rig() != null && shot.rig().view() == View.CAMERA) {
				Pose p = shot.pose(0);
				if (p != null) marker.setPos(p.x(), p.y(), p.z());
			}
		} catch (RuntimeException e) {
			VideocraftLog.LOGGER.error("VIDEOCRAFT error", e);
			finish(mc, false, e.getMessage() == null ? e.toString() : e.getMessage());
		}
	}

	private void go(Step next) {
		VideocraftLog.LOGGER.info("VIDEOCRAFT step {} -> {} ({} s)", step, next, String.format(Locale.ROOT, "%.1f", (System.nanoTime() - stepNanos) / 1e9));
		step = next;
		stepTicks = 0;
		stepNanos = System.nanoTime();
	}

	private void boot(Minecraft mc) {
		if (!(mc.gui.screen() instanceof TitleScreen) || stepTicks < 40) return;
		if (!WorldBoot.frameSize(mc, plan.output().width(), plan.output().height())) {
			if (stepTicks > 200) finish(mc, false, WorldBoot.sizeProblem(mc, plan.output().width(), plan.output().height()));
			return;
		}
		mc.options.pauseOnLostFocus = false;
		levelId = WorldBoot.enter(mc, plan.world(), plan.name());
		VideocraftLog.LOGGER.info("VIDEOCRAFT world {}", levelId);
		go(Step.WORLD);
	}

	private void arrive(Minecraft mc) {
		if (mc.gui.screen() != null || stepTicks < 20) return;
		var p = mc.player;
		// The world spawn point, not where the player happened to land: vanilla scatters the first spawn within the
		// spawn radius at random, so the same seed would put "spawn" somewhere else in every take.
		Vec3 spawn = WorldBoot.spawnPoint(mc);
		anchor("spawn", spawn);
		command(String.format(Locale.ROOT, "tp %s %.3f %.3f %.3f 0 0", p.getName().getString(), spawn.x, spawn.y, spawn.z));
		// The script presses jump itself where a person would; auto-jump would hop at anything brushed in passing.
		mc.options.autoJump().set(false);
		mc.options.guiScale().set(4);
		mc.resizeGui();
		mc.options.particles().set(net.minecraft.server.level.ParticleStatus.ALL);
		var w = plan.world();
		command("time set " + w.time());
		command("weather " + w.weather());
		command("gamerule advance_time false");
		command("gamerule advance_weather false");
		command("difficulty peaceful");
		command("gamemode " + w.gamemode() + " " + p.getName().getString());
		cast = new java.util.LinkedHashMap<>(Cast.stage(plan.actors(), mc));
		go(Step.SETTLE);
	}

	private void settle(Minecraft mc) {
		double seconds = (System.nanoTime() - stepNanos) / 1e9;
		boolean drawn = mc.levelRenderer.hasRenderedAllSections();
		if (seconds < plan.world().settle() || (!drawn && seconds < plan.world().settle() + 30)) return;
		VideocraftLog.LOGGER.info("VIDEOCRAFT settled after {} s, all sections drawn {}", String.format(Locale.ROOT, "%.1f", seconds), drawn);
		mc.gui.toastManager().clear();
		// From here the clock is fixed: staging and shots run on frames, not on wall time.
		fixed = true;
		go(Step.STAGE);
		shot = new ShotRun(this, "stage", 0, 0, plan.world().stage(), false, plan.seed());
	}

	// ---- Frames: staging and shots ----

	private synchronized long frame(long realMs) {
		Minecraft mc = Minecraft.getInstance();
		capture.grab(mc.gameRenderer.mainRenderTarget());
		if (!fixed) return realMs;
		frames++;
		try {
			if (step == Step.STAGE || step == Step.SHOTS) {
				shot.advance();
				if (shot.finished()) nextShot(mc);
			}
		} catch (RuntimeException e) {
			VideocraftLog.LOGGER.error("VIDEOCRAFT error in {}", shot == null ? step : shot.name, e);
			fail((shot == null ? "" : shot.name + ": ") + (e.getMessage() == null ? e.toString() : e.getMessage()));
		}
		if (virtualMs < 0) virtualMs = realMs;
		virtualMs += 1000.0 / plan.output().fps();
		return Math.round(virtualMs);
	}

	private void nextShot(Minecraft mc) {
		if (step == Step.STAGE) go(Step.SHOTS);
		shotIndex++;
		if (shotIndex >= plan.shots().size()) {
			shot = null;
			go(Step.FINISH);
			return;
		}
		Plan.Shot spec = plan.shots().get(shotIndex);
		VideocraftLog.LOGGER.info("VIDEOCRAFT shot {} ({} s)", spec.name(), spec.duration());
		shot = new ShotRun(this, spec.name(), spec.duration(), spec.params().number("preroll", 0), spec.timeline(), true, plan.seed());
		CameraRig rig = registries.rig(spec.camera().string("rig")).create(spec.camera(), shot);
		shot.rig(rig);
		view(mc, rig, spec);
	}

	/** Who holds the camera for this shot (see {@link View}). */
	private void view(Minecraft mc, CameraRig rig, Plan.Shot spec) {
		var p = mc.player;
		String name = p.getName().getString();
		mc.options.fov().set(rig.fov());
		mc.gui.toastManager().clear();
		if (mc.gui.screen() != null) mc.gui.setScreen(null);
		if (rig.view() == View.CAMERA) {
			// An unseen operator: the player is a spectator parked at the camera (so the chunks around it are loaded) and
			// the camera entity is an invisible marker, so the game draws no hand, hotbar or hearts.
			if (parkedFrom == null) parkedFrom = p.position();
			Pose first = rig.pose(shot, 0);
			command("gamemode spectator " + name);
			if (first != null) command(String.format(Locale.ROOT, "tp %s %.3f %.3f %.3f", name, first.x(), first.y(), first.z()));
			if (marker == null || marker.isRemoved() || marker.level() != mc.level) {
				marker = EntityTypes.MARKER.create(mc.level, EntitySpawnReason.COMMAND);
				marker.setId(-7_900_001);
				mc.level.addEntity(marker);
			}
			if (first != null) marker.setPos(first.x(), first.y(), first.z());
			mc.setCameraEntity(marker);
			mc.options.setCameraType(CameraType.FIRST_PERSON);
			mc.options.bobView().set(false);
			hud = false;
		} else {
			if (parkedFrom != null) {
				command(String.format(Locale.ROOT, "tp %s %.3f %.3f %.3f", name, parkedFrom.x, parkedFrom.y, parkedFrom.z));
				parkedFrom = null;
			}
			command("gamemode " + plan.world().gamemode() + " " + name);
			mc.setCameraEntity(p);
			boolean first = rig.view() == View.FIRST;
			mc.options.setCameraType(first ? CameraType.FIRST_PERSON : CameraType.THIRD_PERSON_BACK);
			// View bobbing is the player's own eyes; on a filmed view the game would bob the camera with every step.
			mc.options.bobView().set(first && spec.params().bool("bob", true));
			hud = first && spec.params().bool("hud", true);
		}
	}

	void beginSegment(ShotRun run) {
		if (recordNanos == 0) recordNanos = System.nanoTime();
		capture.begin(run.name, take.shot(run.name), plan.output().fps());
	}

	void endSegment() {
		recordedFrames += Math.round((float) (shot == null ? 0 : shot.duration() * plan.output().fps()));
		capture.end();
	}

	// ---- The end ----

	private void finish(Minecraft mc, boolean pass, String reason) {
		if (step == Step.DONE) return;
		if (shot != null) shot.finish();
		capture.end();
		Step at = step;
		step = Step.DONE;
		current = null;
		JsonObject result = new JsonObject();
		result.addProperty("verdict", pass ? "PASS" : "FAIL");
		if (reason != null) result.addProperty("reason", reason);
		result.addProperty("failedAt", pass ? null : at.name());
		result.addProperty("plan", plan.name());
		result.addProperty("level", levelId);
		result.addProperty("wallSeconds", (System.nanoTime() - startNanos) / 1e9);
		double recording = recordNanos == 0 ? 0 : (System.nanoTime() - recordNanos) / 1e9;
		result.addProperty("recordSeconds", recording);
		JsonArray shots = new JsonArray();
		int total = 0;
		for (Capture.Segment s : capture.segments()) {
			JsonObject o = new JsonObject();
			o.addProperty("name", s.name);
			o.addProperty("frames", s.frames());
			o.addProperty("width", s.width());
			o.addProperty("height", s.height());
			o.addProperty("ffmpegExit", s.exitCode());
			o.addProperty("video", take.dir().relativize(s.video()).toString());
			shots.add(o);
			total += s.frames();
		}
		result.addProperty("captureFps", recording == 0 ? 0 : total / recording);
		result.add("shots", shots);
		take.writeResult(result);
		VideocraftLog.LOGGER.info("VIDEOCRAFT RESULT {}{}", pass ? "PASS" : "FAIL", reason == null ? " " + total + " frames" : " " + reason);
		mc.execute(mc::stop);
	}

	/** Keeps the director's view of the shot list for the result. */
	List<Plan.Shot> shots() { return plan.shots(); }
}
