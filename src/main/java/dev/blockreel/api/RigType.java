package dev.blockreel.api;

/** Makes a camera rig from the {@code camera} table of a shot, when the shot is prepared. */
@FunctionalInterface
public interface RigType {
	CameraRig create(Params params, ShotContext shot);
}
