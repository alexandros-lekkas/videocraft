package io.github.alexandroslekkas.videocraft.api;

/**
 * Who holds the camera in a shot, and where it is each frame. Called once per rendered frame with the shot's clock
 * ({@link ShotContext#seconds()}), so a rig is a function of time plus whatever it reads from the world.
 */
public interface CameraRig {
	/** How the shot is seen: an unseen operator, an operator filming the player, or the player's own eyes. */
	View view();

	/** The camera for this frame, or null to leave the game's own camera (always null for {@link View#FIRST}). */
	Pose pose(ShotContext shot, float partialTick);

	/** Field of view in degrees for this shot (the game's own FOV option, 30–110). */
	default int fov() { return 70; }
}
