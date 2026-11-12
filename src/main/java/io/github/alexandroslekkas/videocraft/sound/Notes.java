package io.github.alexandroslekkas.videocraft.sound;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * A melody for note blocks, written as text: {@code "c4 e4 g4 - c5*2 e4+g4"}. One token per step; {@code -} is a rest,
 * {@code *n} holds a note for n steps (note blocks cannot sustain, so the rest of the hold is silence), {@code +} plays
 * several notes at once. Notes are named at harp pitch (a note block's range is F#3 to F#5, the block's {@code note}
 * values 0 to 24); a bare number 0-24 is a note value. Plain Java, so the smoke checks can run it without the game.
 */
public final class Notes {
	/** One sounding note: when (in steps from the start) and which note block value (0-24). */
	public record Note(int step, int value) {}

	/** The parsed melody: its notes in order and its length in steps (rests and holds included). */
	public record Melody(List<Note> notes, int steps) {}

	private static final int FS3 = 54;

	private Notes() {}

	public static Melody parse(String text) {
		List<Note> notes = new ArrayList<>();
		int step = 0;
		for (String token : text.trim().split("\\s+")) {
			if (token.isEmpty()) continue;
			int hold = 1;
			int star = token.indexOf('*');
			if (star >= 0) {
				try {
					hold = Integer.parseInt(token.substring(star + 1));
				} catch (NumberFormatException e) {
					throw new IllegalArgumentException("note '" + token + "': after * comes a whole number of steps");
				}
				if (hold < 1 || hold > 64) throw new IllegalArgumentException("note '" + token + "': a hold is 1 to 64 steps");
				token = token.substring(0, star);
			}
			if (!token.equals("-")) for (String name : token.split("\\+")) notes.add(new Note(step, value(name)));
			step += hold;
		}
		if (notes.isEmpty()) throw new IllegalArgumentException("notes: no notes (write them like \"c4 e4 g4 - c5\")");
		return new Melody(List.copyOf(notes), step);
	}

	/** A note name (c4, f#3, bb4) or a note value (0-24) as the note block value 0-24. */
	public static int value(String name) {
		String n = name.toLowerCase(Locale.ROOT);
		if (n.matches("\\d{1,2}")) return check(Integer.parseInt(n), name);
		if (!n.matches("[a-g][#b]?-?\\d")) throw new IllegalArgumentException("note '" + name + "': write a name like c4, f#3, bb4, a rest '-', or a value 0-24");
		int semitone = switch (n.charAt(0)) {
			case 'c' -> 0; case 'd' -> 2; case 'e' -> 4; case 'f' -> 5; case 'g' -> 7; case 'a' -> 9; default -> 11;
		};
		int i = 1;
		if (n.charAt(i) == '#') { semitone++; i++; } else if (n.charAt(i) == 'b') { semitone--; i++; }
		int octave = Integer.parseInt(n.substring(i));
		return check((octave + 1) * 12 + semitone - FS3, name);
	}

	private static int check(int value, String name) {
		if (value < 0 || value > 24) throw new IllegalArgumentException("note '" + name + "' is outside a note block's range (f#3 to f#5, values 0-24)");
		return value;
	}

	/** The playback rate of a note value, as vanilla's note block: 2^((value - 12) / 12). */
	public static float pitch(int value) {
		return (float) Math.pow(2, (value - 12) / 12.0);
	}
}
