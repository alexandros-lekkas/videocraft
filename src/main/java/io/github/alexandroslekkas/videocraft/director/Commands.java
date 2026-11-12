package io.github.alexandroslekkas.videocraft.director;

import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.api.Action;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import net.minecraft.client.Minecraft;
import net.minecraft.commands.CommandSource;
import net.minecraft.commands.CommandSourceStack;
import net.minecraft.network.chat.Component;
import net.minecraft.server.MinecraftServer;
import net.minecraft.world.phys.Vec3;

import java.util.List;
import java.util.concurrent.CompletableFuture;

/**
 * Commands on the integrated server, checked. Every command runs as the server, positioned at the {@code spawn}
 * anchor (so {@code ~ ~ ~} is where the player arrived), with its output kept: a command that fails says why, and the
 * {@code command} action fails the take with the first one (its index and the game's own message). Long lists (a
 * set is thousands of fills) run in batches of a few milliseconds of server time per frame, so the game keeps
 * drawing while it builds; the action is over when the last batch has run.
 */
final class Commands {
	private Commands() {}

	/** Milliseconds of server time one batch may take. */
	static final long BATCH_MS = 30;

	/** Runs one command on the server thread (call it there); returns the failure text, or null if it worked. */
	static String run(MinecraftServer server, Vec3 at, String command) {
		StringBuilder failure = new StringBuilder();
		boolean[] failed = {false};
		CommandSource capture = new CommandSource() {
			@Override public void sendSystemMessage(Component message) {
				if (!failure.isEmpty()) failure.append("; ");
				failure.append(message.getString());
			}
			@Override public boolean acceptsSuccess() { return false; }
			@Override public boolean acceptsFailure() { return true; }
			@Override public boolean shouldInformAdmins() { return false; }
		};
		CommandSourceStack source = server.createCommandSourceStack().withSource(capture).withCallback((success, result) -> { if (!success) failed[0] = true; });
		if (at != null) source = source.withPosition(at);
		server.getCommands().performPrefixedCommand(source, command);
		if (failure.isEmpty() && !failed[0]) return null;
		return failure.isEmpty() ? "the command did not succeed" : failure.toString();
	}

	/** Where commands run: the spawn anchor once it exists. */
	static Vec3 origin() {
		Director d = Director.current();
		try {
			return d == null ? null : d.anchor("spawn");
		} catch (IllegalArgumentException e) {
			return null;
		}
	}

	/**
	 * {@code {do = "command", command = ".."}} or {@code commands = [..]}; {@code forceload = [x1, z1, x2, z2]} keeps
	 * those chunks loaded for the rest of the take and waits until they are before running anything; {@code strict =
	 * false} carries on past failures (logged).
	 */
	static Action action(Params p, ShotContext shot) {
		List<String> commands = p.has("commands") ? p.strings("commands") : List.of(p.string("command"));
		if (commands.isEmpty()) throw new IllegalArgumentException(p.where() + ": commands is empty");
		int[] area = null;
		if (p.has("forceload")) {
			double[] f = p.numbers("forceload");
			if (f.length != 4) throw new IllegalArgumentException(p.where() + ": forceload = [x1, z1, x2, z2]");
			area = new int[] {(int) Math.floor(Math.min(f[0], f[2])), (int) Math.floor(Math.min(f[1], f[3])), (int) Math.floor(Math.max(f[0], f[2])), (int) Math.floor(Math.max(f[1], f[3]))};
			if ((area[2] - area[0]) / 16 * ((area[3] - area[1]) / 16) > 4096) throw new IllegalArgumentException(p.where() + ": forceload covers more than 4096 chunks");
		}
		return new Batches(p.where(), commands, area, p.bool("strict", true));
	}

	private static final class Batches implements Action {
		private final String where;
		private final List<String> commands;
		private final int[] area;
		private final boolean strict;
		private CompletableFuture<Integer> pending;
		private boolean loaded;
		private int next, waited;
		private volatile String error;

		Batches(String where, List<String> commands, int[] area, boolean strict) {
			this.where = where;
			this.commands = commands;
			this.area = area;
			this.strict = strict;
			this.loaded = area == null;
		}

		@Override
		public boolean frame(ShotContext shot) {
			MinecraftServer server = Minecraft.getInstance().getSingleplayerServer();
			if (server == null) { shot.fail(where + ": no integrated server for commands"); return true; }
			if (pending != null && !pending.isDone()) return false;
			if (pending != null) {
				next = pending.join();
				pending = null;
				if (error != null) {
					if (strict) { shot.fail(error); return true; }
					VideocraftLog.LOGGER.warn("VIDEOCRAFT {}", error);
					error = null;
				}
			}
			Vec3 at = origin();
			if (!loaded) {
				// Forceload once, then wait (a frame at a time) until every chunk of the area is there.
				int[] a = area;
				if (waited++ == 0) {
					pending = server.submit(() -> {
						// Vanilla's forceload takes at most 256 chunks a command: add the area in tiles of 16x16 chunks.
						for (int x = a[0]; x <= a[2]; x = Math.floorDiv(x, 16) * 16 + 256) {
							for (int z = a[1]; z <= a[3]; z = Math.floorDiv(z, 16) * 16 + 256) {
								int x2 = Math.min(a[2], Math.floorDiv(x, 16) * 16 + 255), z2 = Math.min(a[3], Math.floorDiv(z, 16) * 16 + 255);
								String e = run(server, at, "forceload add " + x + " " + z + " " + x2 + " " + z2);
								if (e != null && !e.contains("already") && !e.contains("No chunks were marked") && error == null) error = where + ": forceload failed: " + e;
							}
						}
						return 0;
					});
					return false;
				}
				pending = server.submit(() -> server.overworld().hasChunksAt(a[0], a[1], a[2], a[3]) ? 1 : 0);
				if (pending.join() == 1) loaded = true;
				pending = null;
				if (!loaded && waited > 60 * 120) { shot.fail(where + ": the forceloaded chunks did not load in two minutes"); return true; }
				if (!loaded) return false;
			}
			if (next >= commands.size()) return true;
			int from = next;
			pending = server.submit(() -> {
				long end = System.nanoTime() + BATCH_MS * 1_000_000;
				int i = from;
				while (i < commands.size()) {
					String command = commands.get(i);
					String e = run(server, at, command);
					i++;
					if (e != null) {
						error = where + ": command " + (i - 1) + " of " + commands.size() + " failed: \"" + shorten(command) + "\": " + e;
						if (strict) break;
						return i;
					}
					if (System.nanoTime() > end) break;
				}
				return i;
			});
			return false;
		}

		private static String shorten(String command) {
			return command.length() <= 160 ? command : command.substring(0, 157) + "...";
		}
	}
}
