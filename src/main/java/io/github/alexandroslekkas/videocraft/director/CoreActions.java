package io.github.alexandroslekkas.videocraft.director;

import io.github.alexandroslekkas.videocraft.api.Registry;

/** The actions every take has: run commands, note a beat for the edit, wait. Owned by the mod runtime. */
final class CoreActions {
	private CoreActions() {}

	static void register(Registry r) {
		// {do = "command", command = "time set 6000"} or {do = "command", commands = [..], forceload = [x1, z1, x2, z2]}.
		// Checked and batched across frames; the take fails with the first command that errors (Commands).
		r.action("command", Commands::action);
		// {do = "mark", label = "impact"}: notes this frame in marks.json.
		r.action("mark", (p, shot) -> {
			String label = p.string("label");
			return s -> { s.mark(label); return true; };
		});
		// {do = "stand_in", id = "dummy", at = [..]}: a subject for checking camera rigs (StandIn), in world.stage.
		r.action("stand_in", (p, shot) -> {
			StandIn s = StandIn.stage(p, shot);
			Director.current().addActor(s);
			return x -> true;
		});
		// {do = "glide", actor = "dummy", path = [..], speed = 1.4}: moves a stand-in exactly along a curve.
		r.action("glide", (p, shot) -> {
			String who = p.string("actor");
			if (!(shot.actor(who) instanceof StandIn s)) throw new IllegalArgumentException(p.where() + ": glide moves a stand_in, and '" + who + "' is not one");
			return StandIn.glide(p, shot, s);
		});
		// {do = "wait", seconds = 1.5}: holds the timeline of a staging block (shots end on their duration anyway).
		r.action("wait", (p, shot) -> {
			double until = shot.seconds() + p.number("seconds");
			return s -> s.seconds() >= until;
		});
	}
}
