package io.github.alexandroslekkas.videocraft.api;

import net.minecraft.client.Minecraft;
import net.minecraft.world.phys.Vec3;

import java.util.Random;

/**
 * What an action or a rig can see and do during a shot. Everything runs on the render thread. Times are on the take's
 * fixed clock: {@link #seconds()} advances exactly 1/fps per captured frame, however long a frame takes in real time.
 */
public interface ShotContext {
	Minecraft minecraft();

	/** The shot's name from the script. */
	String shot();

	/** Frames since this shot started recording; 0 while it is being prepared. */
	int frame();

	/** {@link #frame()} in seconds. */
	double seconds();

	/** The shot's planned length in seconds. */
	double duration();

	/** Whether frames are being captured (false while a shot is prepared and during world staging). */
	boolean recording();

	int fps();

	/** A named point: {@code spawn} (the player's feet on arrival) or one the script or an action defined. */
	Vec3 anchor(String name);

	/** Defines (or moves) a named point for the rest of the take. */
	void anchor(String name, Vec3 at);

	/**
	 * Resolves a position parameter: {@code [x, y, z]}, {@code {anchor = "spawn", offset = [x, y, z]}}, or a point on
	 * an actor where it stands now, {@code {actor = "nibs", offset = [x, y, z]}} in world axes or
	 * {@code {actor = "nibs", front = 3, right = 0.5, up = 1.2}} along the way it faces.
	 */
	Vec3 position(Params params, String key);

	/** An actor by id ({@code player} always exists). Throws if the script never staged it. */
	Actor actor(String id);

	/** Runs a command on the integrated server, as the server, with its output suppressed. */
	void command(String command);

	/** Notes the current frame under {@code label} in this shot's marks.json, for the edit and the measurements. */
	void mark(String label);

	/** Notes a value (where something is in the frame, a distance) under {@code label}. */
	void mark(String label, double value);

	/** Seeded per take and shot: the same script and seed give the same take. */
	Random random();

	/** The camera pose of the frame being rendered, or of the last one. */
	Pose camera();

	/** Ends the take as FAIL with this reason; nothing is cut from a broken take. */
	void fail(String reason);
}
