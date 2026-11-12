package io.github.alexandroslekkas.videocraft.api;

/**
 * Makes one action from its cue in the script. Called when the cue's time comes, on the render thread. Validate the
 * parameters here and throw {@link IllegalArgumentException} with a message an agent can act on: the take fails with it.
 */
@FunctionalInterface
public interface ActionType {
	Action create(Params params, ShotContext shot);
}
