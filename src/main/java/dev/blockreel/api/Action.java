package dev.blockreel.api;

/**
 * Something that happens on a shot's timeline: a walk, a look, a caption, a command. Created when its cue's time comes,
 * then called once per captured frame (on the render thread, inside the fixed-step clock) until it says it is done.
 * Keep per-frame work cheap: it runs inside the frame budget.
 */
public interface Action {
	/** One frame of the action. Return true when it is finished; an instant action returns true at once. */
	boolean frame(ShotContext shot);

	/** The shot ended (or the take failed) while this action was still running. Release keys, remove what you added. */
	default void stop(ShotContext shot) {}
}
