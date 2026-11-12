package io.github.alexandroslekkas.videocraft.sound;

import java.util.List;

/**
 * Sounds the game does not have, which the mix synthesizes (cli/videocraft/audio/sfx.py makes the same list): a script
 * plays them as {@code videocraft:<name>} with the {@code sound} or {@code ambience} action and they are logged like
 * any other sound. Original audio, so they are also in exports made without any game asset.
 */
public final class Synth {
	public static final List<String> EVENTS = List.of("kick", "snare", "hat", "crash", "ding", "dun", "sting", "cricket", "pop", "whoosh", "boing");

	private Synth() {}
}
