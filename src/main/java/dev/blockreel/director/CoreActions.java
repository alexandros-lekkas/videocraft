package dev.blockreel.director;

import dev.blockreel.api.Registry;

/** The actions every take has: run commands, note a beat for the edit, wait. Owned by the mod runtime. */
final class CoreActions {
	private CoreActions() {}

	static void register(Registry r) {
		// {do = "command", command = "time set 6000"} or {do = "command", commands = [..]}: instant, on the server.
		r.action("command", (p, shot) -> {
			var commands = p.has("commands") ? p.strings("commands") : java.util.List.of(p.string("command"));
			return s -> { commands.forEach(s::command); return true; };
		});
		// {do = "mark", label = "impact"}: notes this frame in marks.json.
		r.action("mark", (p, shot) -> {
			String label = p.string("label");
			return s -> { s.mark(label); return true; };
		});
		// {do = "wait", seconds = 1.5}: holds the timeline of a staging block (shots end on their duration anyway).
		r.action("wait", (p, shot) -> {
			double until = shot.seconds() + p.number("seconds");
			return s -> s.seconds() >= until;
		});
	}
}
