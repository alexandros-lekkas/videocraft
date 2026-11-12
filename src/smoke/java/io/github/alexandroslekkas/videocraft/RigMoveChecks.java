package io.github.alexandroslekkas.videocraft;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import io.github.alexandroslekkas.videocraft.api.Actor;
import io.github.alexandroslekkas.videocraft.api.CameraRig;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.Pose;
import io.github.alexandroslekkas.videocraft.api.RigType;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import io.github.alexandroslekkas.videocraft.camera.Probe;
import io.github.alexandroslekkas.videocraft.camera.Rigs;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Random;

/**
 * Every camera rig against synthetic subjects, without Minecraft: a walker that starts from rest, curves, hops (its
 * ground reference does not) and stops. Each rig must move without a frame-to-frame jump in position or angle, keep
 * its subject in frame, and the lead track must keep it in the middle third at a steady size and stay in front of a
 * wall. Run by {@code ./gradlew check} with RigChecks.
 */
public final class RigMoveChecks {
	static final int FPS = 60;
	static final double DURATION = 8;

	/** A subject on a scripted path: f(t) gives ground point and heading. */
	static final class Walker implements Actor {
		final String id;
		final java.util.function.DoubleFunction<double[]> path;
		double t;

		Walker(String id, java.util.function.DoubleFunction<double[]> path) { this.id = id; this.path = path; }

		@Override public String id() { return id; }
		@Override public Entity entity() { return null; }
		@Override public Vec3 ground() { double[] p = path.apply(t); return new Vec3(p[0], p[1], p[2]); }
		@Override public float heading() { return (float) path.apply(t)[3]; }
		@Override public Vec3 head() { return ground().add(Vec3.directionFromRotation(0, heading()).scale(0.3)).add(0, 1.6, 0); }
		@Override public Vec3 velocity() {
			double[] a = path.apply(t - 0.01), b = path.apply(t + 0.01);
			return new Vec3((b[0] - a[0]) / 0.02, 0, (b[2] - a[2]) / 0.02);
		}
	}

	/** Distance walked at time t: from rest, eased up to 1.4 b/s over 0.5 s, steady, eased to a stop by t = 6.5. */
	static double walked(double t) {
		double v = 1.4, e = 0.5, stop = 6.5;
		java.util.function.DoubleUnaryOperator ramp = k -> k * k * k - k * k * k * k / 2;
		if (t <= 0) return 0;
		if (t < e) return v * e * ramp.applyAsDouble(t / e);
		double cruiseEnd = stop - e;
		if (t < cruiseEnd) return v * e / 2 + (t - e) * v;
		double total = v * e / 2 + (cruiseEnd - e) * v + v * e / 2;
		if (t >= stop) return total;
		return total - v * e * ramp.applyAsDouble((stop - t) / e);
	}

	/** Along an arc of radius 12 to the left, heading the way it goes. */
	static double[] arc(double t, double x0, double z0) {
		double s = walked(t), r = 12, a = s / r;
		double x = x0 + r * (1 - Math.cos(a)), z = z0 + r * Math.sin(a);
		// Heading of travel (dx, dz) = (sin a, cos a): Minecraft yaw = atan2(dz, dx) - 90.
		double yaw = Math.toDegrees(Math.atan2(Math.cos(a), Math.sin(a))) - 90;
		return new double[] {x, 64, z, yaw};
	}

	static final class Shot implements ShotContext {
		final Map<String, Actor> actors = new HashMap<>();
		int frame;
		final Random random = new Random(3);

		@Override public Minecraft minecraft() { return null; }
		@Override public String shot() { return "check"; }
		@Override public int frame() { return frame; }
		@Override public double seconds() { return frame / (double) FPS; }
		@Override public double duration() { return DURATION; }
		@Override public boolean recording() { return frame >= 0; }
		@Override public int fps() { return FPS; }
		@Override public Vec3 anchor(String name) { return Vec3.ZERO; }
		@Override public void anchor(String name, Vec3 at) {}
		@Override public Vec3 position(Params p, String key) {
			var e = p.raw(key);
			if (e == null) throw new IllegalArgumentException(p.where() + ": missing position '" + key + "'");
			if (e.isJsonArray()) { var a = e.getAsJsonArray(); return new Vec3(a.get(0).getAsDouble(), a.get(1).getAsDouble(), a.get(2).getAsDouble()); }
			var o = e.getAsJsonObject();
			Vec3 base = o.has("actor") ? actor(o.get("actor").getAsString()).ground() : Vec3.ZERO;
			if (o.has("offset")) { var a = o.getAsJsonArray("offset"); base = base.add(a.get(0).getAsDouble(), a.get(1).getAsDouble(), a.get(2).getAsDouble()); }
			return base;
		}
		@Override public Actor actor(String id) {
			Actor a = actors.get(id);
			if (a == null) throw new IllegalArgumentException("no actor " + id);
			return a;
		}
		@Override public void command(String command) {}
		@Override public void mark(String label) {}
		@Override public void mark(String label, double value) {}
		@Override public Random random() { return random; }
		@Override public Pose camera() { return null; }
		@Override public void fail(String reason) { throw new AssertionError(reason); }
	}

	record Run(List<Pose> poses, List<Double> fovs, Shot shot) {}

	/** Films {@code DURATION} seconds (after one second of pre-roll) with the rig made from {@code json}. */
	static Run film(String json, RigType type, Shot shot) {
		JsonObject o = JsonParser.parseString(json).getAsJsonObject();
		CameraRig rig = type.create(new Params(o, "check"), shot);
		List<Pose> poses = new ArrayList<>();
		List<Double> fovs = new ArrayList<>();
		for (int f = -FPS; f < DURATION * FPS; f++) {
			shot.frame = f;
			for (Actor a : shot.actors.values()) if (a instanceof Walker w) w.t = f / (double) FPS;
			Pose p = rig.pose(shot, 0);
			if (f >= 0) { poses.add(p); fovs.add(rig.fov(shot)); }
		}
		return new Run(poses, fovs, shot);
	}

	static Shot walkers() {
		Shot s = new Shot();
		s.actors.put("nibs", new Walker("nibs", t -> arc(t, 0, 0)));
		s.actors.put("duke", new Walker("duke", t -> arc(t, 3, 0)));
		// Hops twice: the heading wobbles a little like a body does, the ground reference stays flat.
		s.actors.put("hopper", new Walker("hopper", t -> { double[] p = arc(t, 0, 0); p[3] += 4 * Math.sin(t * 9); return p; }));
		return s;
	}

	/** No jump between frames: position at most {@code step} blocks, angles at most {@code turn} degrees, and no jolt. */
	static void smooth(String name, Run run, double step, double turn) {
		double maxJolt = 0;
		for (int i = 2; i < run.poses.size(); i++) {
			Pose a = run.poses.get(i - 2), b = run.poses.get(i - 1), c = run.poses.get(i);
			double d = b.eye().distanceTo(c.eye());
			double dy = Math.abs(wrap(c.yaw() - b.yaw())), dp = Math.abs(c.pitch() - b.pitch());
			PlanChecks.check(d <= step, name + ": camera jumps " + fmt(d) + " blocks at frame " + i);
			PlanChecks.check(dy <= turn && dp <= turn, name + ": camera turns " + fmt(Math.max(dy, dp)) + " degrees at frame " + i);
			// Change of velocity between frames, in blocks per second per frame.
			Vec3 v1 = b.eye().subtract(a.eye()), v2 = c.eye().subtract(b.eye());
			maxJolt = Math.max(maxJolt, v2.subtract(v1).length() * FPS);
		}
		PlanChecks.check(maxJolt < 0.35, name + ": camera speed changes by " + fmt(maxJolt) + " blocks/s in one frame");
	}

	/** Where {@code point} falls in the frame of {@code pose}: {x, y} in -1..1 (centre 0), and depth. */
	static double[] project(Pose pose, Vec3 point, double fov) {
		Vec3 d = point.subtract(pose.eye());
		double yaw = Math.toRadians(pose.yaw()), pitch = Math.toRadians(pose.pitch());
		Vec3 fwd = new Vec3(-Math.sin(yaw) * Math.cos(pitch), -Math.sin(pitch), Math.cos(yaw) * Math.cos(pitch));
		Vec3 right = new Vec3(-Math.cos(yaw), 0, -Math.sin(yaw));
		Vec3 up = right.cross(fwd).scale(-1);
		double z = d.dot(fwd), t = Math.tan(Math.toRadians(fov) / 2);
		return new double[] {d.dot(right) / z / (t * 16 / 9.0), d.dot(up) / z / t, z};
	}

	static void inFrame(String name, Run run, String subject, double limit, int from, int to) {
		Walker w = (Walker) run.shot.actors.get(subject);
		for (int i = from; i < to; i++) {
			w.t = i / (double) FPS;
			double[] p = project(run.poses.get(i), w.ground().add(0, 0.9, 0), run.fovs.get(i));
			PlanChecks.check(p[2] > 0 && Math.abs(p[0]) <= limit && Math.abs(p[1]) <= 1, name + ": " + subject + " at " + fmt(p[0]) + "," + fmt(p[1]) + " of the frame at frame " + i);
		}
	}

	public static void main(String[] args) {
		Rigs.probe = Probe.OPEN;
		Map<String, RigType> rigs = new HashMap<>();
		Rigs.register(new io.github.alexandroslekkas.videocraft.api.Registry() {
			@Override public void action(String id, io.github.alexandroslekkas.videocraft.api.ActionType type) {}
			@Override public void rig(String id, RigType type) { rigs.put(id, type); }
		});
		int walking = (int) (5.8 * FPS);

		// lead: in the middle third, a steady size while walking, and it eases to a stop with the subject.
		Run lead = film("{\"rig\":\"lead\",\"subject\":\"nibs\",\"distance\":4}", rigs.get("lead"), walkers());
		smooth("lead", lead, 0.06, 1.5);
		inFrame("lead", lead, "nibs", 1 / 3.0, 0, lead.poses.size());
		Walker nibs = (Walker) lead.shot.actors.get("nibs");
		double min = 1e9, max = 0;
		for (int i = FPS; i < walking; i++) {
			nibs.t = i / (double) FPS;
			double d = lead.poses.get(i).eye().distanceTo(nibs.ground().add(0, 1, 0));
			min = Math.min(min, d);
			max = Math.max(max, d);
		}
		PlanChecks.check(max / min < 1.1, "lead: subject distance varies " + fmt(min) + " to " + fmt(max) + " while walking");
		// After the stop the camera comes to rest too, and never turns back toward the subject (no pumping).
		Pose last = lead.poses.getLast(), before = lead.poses.get(lead.poses.size() - 2);
		PlanChecks.check(last.eye().distanceTo(before.eye()) < 1e-3, "lead: camera still moving after the subject stopped");
		Run hop = film("{\"rig\":\"lead\",\"subject\":\"hopper\",\"distance\":4,\"swing\":true}", rigs.get("lead"), walkers());
		smooth("lead swing", hop, 0.06, 1.5);

		// lead keeps in front of a wall: a plane at z = 9 that the subject walks toward (blocks camera beyond it).
		Rigs.probe = (from, to) -> {
			double wall = 9;
			if ((from.z - wall) * (to.z - wall) >= 0) return from.distanceTo(to);
			return from.distanceTo(to) * Math.abs(wall - from.z) / Math.abs(to.z - from.z);
		};
		Run walled = film("{\"rig\":\"lead\",\"subject\":\"nibs\",\"distance\":4}", rigs.get("lead"), walkers());
		for (int i = 0; i < walled.poses.size(); i++)
			PlanChecks.check(walled.poses.get(i).z() < 9 - 0.05, "lead: camera through the wall at frame " + i + ": z " + fmt(walled.poses.get(i).z()));
		smooth("lead walled", walled, 0.08, 2.5);
		Rigs.probe = Probe.OPEN;

		Run chase = film("{\"rig\":\"chase\",\"subject\":\"nibs\"}", rigs.get("chase"), walkers());
		smooth("chase", chase, 0.06, 1.5);
		inFrame("chase", chase, "nibs", 0.5, 0, chase.poses.size());
		Run track = film("{\"rig\":\"track\",\"subject\":\"nibs\",\"side\":\"left\"}", rigs.get("track"), walkers());
		smooth("track", track, 0.06, 1.5);
		inFrame("track", track, "nibs", 0.6, 0, track.poses.size());
		Run dolly = film("{\"rig\":\"dolly\",\"from\":[-6,65.5,-4],\"to\":[6,65.5,-4],\"subject\":\"nibs\"}", rigs.get("dolly"), walkers());
		smooth("dolly", dolly, 0.06, 1.5);
		Run crane = film("{\"rig\":\"crane\",\"eye\":[0,65,-6],\"rise\":6,\"at\":[0,64,4]}", rigs.get("crane"), walkers());
		smooth("crane", crane, 0.06, 1.5);
		PlanChecks.check(Math.abs(crane.poses.getLast().y() - 71) < 1e-3, "crane: rises to 71, not " + crane.poses.getLast().y());
		Run locked = film("{\"rig\":\"locked\",\"eye\":[-6,66,2],\"subject\":\"nibs\"}", rigs.get("locked"), walkers());
		smooth("locked", locked, 1e-9, 1.5);
		inFrame("locked", locked, "nibs", 0.6, 0, locked.poses.size());
		Run two = film("{\"rig\":\"two_shot\",\"subjects\":[\"nibs\",\"duke\"]}", rigs.get("two_shot"), walkers());
		smooth("two_shot", two, 0.06, 1.5);
		inFrame("two_shot", two, "nibs", 0.9, 0, two.poses.size());
		inFrame("two_shot", two, "duke", 0.9, 0, two.poses.size());
		Run face = film("{\"rig\":\"face\",\"subject\":\"nibs\",\"distance\":0.3}", rigs.get("face"), walkers());
		smooth("face", face, 0.06, 2);
		for (int i = 0; i < face.poses.size(); i++) {
			nibs = (Walker) face.shot.actors.get("nibs");
			nibs.t = i / (double) FPS;
			PlanChecks.check(face.poses.get(i).eye().distanceTo(nibs.head()) > 0.5, "face: lens inside the model at frame " + i);
		}
		Run zoom = film("{\"rig\":\"fixed\",\"eye\":[0,66,-6],\"at\":{\"actor\":\"nibs\"},\"fov\":[70,40],\"drift\":0.4}", rigs.get("fixed"), walkers());
		smooth("fixed drift", zoom, 1e-9, 0.05);
		PlanChecks.check(zoom.fovs.getFirst() == 70 && Math.abs(zoom.fovs.getLast() - 40) < 0.1, "fov eases from 70 to 40: " + zoom.fovs.getLast());
		Run orbit = film("{\"rig\":\"orbit\",\"center\":{\"actor\":\"nibs\"},\"radius\":6}", rigs.get("orbit"), walkers());
		smooth("orbit", orbit, 0.06, 1.5);

		// Bad parameters are refused with the key's name.
		String[][] bad = {{"lead", "{\"distance\":4}", "subject"}, {"lead", "{\"subject\":\"nibs\",\"fov\":150}", "fov"}, {"track", "{\"subject\":\"nibs\",\"side\":\"up\"}", "side"},
			{"two_shot", "{\"subjects\":[\"nibs\"]}", "subjects"}, {"dolly", "{\"from\":[0,0,0],\"to\":[1,0,0]}", "subject"}};
		for (String[] b : bad) {
			String message = "";
			try {
				rigs.get(b[0]).create(new Params(JsonParser.parseString(b[1]).getAsJsonObject(), "shots.x.camera"), walkers());
			} catch (IllegalArgumentException e) {
				message = e.getMessage();
			}
			PlanChecks.check(message.contains("shots.x.camera") && message.contains(b[2]), b[0] + " " + b[1] + " is refused naming " + b[2] + ", got: " + message);
		}
		System.out.println("RigMoveChecks PASS " + rigs.size() + " rigs");
	}

	static double wrap(double d) { d %= 360; return d > 180 ? d - 360 : d < -180 ? d + 360 : d; }

	static String fmt(double d) { return String.format(java.util.Locale.ROOT, "%.3f", d); }
}
