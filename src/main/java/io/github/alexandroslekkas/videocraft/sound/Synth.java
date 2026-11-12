package io.github.alexandroslekkas.videocraft.sound;

import java.util.List;

/**
 * Sounds the game does not have, which the mix synthesizes (cli/videocraft/audio/sfx.py makes the same list): a script
 * plays them as {@code videocraft:<name>} with the {@code sound} or {@code ambience} action and they are logged like
 * any other sound. Original audio, so they are also in exports made without any game asset. So are the library's
 * sounds, {@code videocraft:lib/<name>}, which the compiler checks against the library's index.
 */
public final class Synth {
	public static final List<String> EVENTS = List.of("kick", "snare", "hat", "crash", "ding", "dun", "sting", "cricket", "pop", "whoosh", "boing");
	/** {@code videocraft:lib/<name>}: a sound of the original library (cli/videocraft/audio/library/library.toml). */
	public static final String LIBRARY = "lib/";

	private Synth() {}
}
