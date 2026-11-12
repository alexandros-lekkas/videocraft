package dev.blockreel.api;

/** Where built-ins and plugins register what a shot script can name. Registering an id twice is an error. */
public interface Registry {
	/** A timeline action ({@code do = "<id>"} in a shot's timeline, or in {@code [world] stage}). */
	void action(String id, ActionType type);

	/** A camera rig ({@code camera.rig = "<id>"}). */
	void rig(String id, RigType type);
}
