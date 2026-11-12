package io.github.alexandroslekkas.videocraft.text;

import io.github.alexandroslekkas.videocraft.api.Registry;

/**
 * The text actions of the shot script (docs/SCRIPT.md, "Text"): {@code caption}, {@code title}, {@code card},
 * {@code lower_third}, {@code keycap}, {@code clear}. Each validates its parameters when the cue is read and draws nothing
 * until its first frame. Owned by workstream (c).
 */
public final class TextActions {
	private TextActions() {}

	public static void register(Registry r) {
		r.action("caption", (p, shot) -> new Caption(p));
		r.action("title", (p, shot) -> new Title("title", p));
		r.action("card", (p, shot) -> new Title("card", p));
		r.action("lower_third", (p, shot) -> new LowerThird(p));
		r.action("keycap", (p, shot) -> new Keycap(p));
		// {do = "clear"} takes everything off at once; what = "message" or "keycap" takes one slot.
		r.action("clear", (p, shot) -> {
			String what = p.string("what", "all");
			Message.Slot slot = switch (what) {
				case "all" -> null;
				case "message" -> Message.Slot.MESSAGE;
				case "keycap" -> Message.Slot.KEYCAP;
				default -> throw new IllegalArgumentException(p.where() + ": what is \"all\", \"message\" or \"keycap\"");
			};
			return s -> { TextLayer.clearMessages(slot); return true; };
		});
	}
}
