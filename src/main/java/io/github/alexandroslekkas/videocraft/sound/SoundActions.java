package io.github.alexandroslekkas.videocraft.sound;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import io.github.alexandroslekkas.videocraft.api.Action;
import io.github.alexandroslekkas.videocraft.api.Params;
import io.github.alexandroslekkas.videocraft.api.Registry;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import net.minecraft.client.Minecraft;
import net.minecraft.client.resources.sounds.SimpleSoundInstance;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.core.BlockPos;
import net.minecraft.core.particles.ParticleOptions;
import net.minecraft.core.particles.ParticleType;
import net.minecraft.core.particles.ParticleTypes;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.resources.Identifier;
import net.minecraft.sounds.SoundSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.block.NoteBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.NoteBlockInstrument;
import net.minecraft.world.phys.Vec3;

import java.util.ArrayList;
import java.util.List;
import java.util.Random;

/**
 * The audio workstream's actions. Everything that should be heard is played through the client's sound system on the
 * frame it happens (and so lands in {@link SoundLog}); the muted game never makes it audible itself.
 * <ul>
 * <li>{@code sound}: one sound event at {@code pos}, at an actor, or {@code relative} (not positional).</li>
 * <li>{@code tune}: a melody on note blocks, each note on its frame with the block's real sound and note particle.</li>
 * <li>{@code ambience}: a bed of one sound event repeated with seeded jitter in time, pitch and place.</li>
 * <li>{@code particles}: a burst (or a stream) of a simple particle at a position or an actor.</li>
 * </ul>
 * Positions are {@code pos} (the cue's {@code at} is its time). Events in the {@code videocraft:} namespace
 * ({@code videocraft:kick}, {@code videocraft:cricket}, see docs/SCRIPT.md) are synthesized by the mix, not the game.
 */
public final class SoundActions {
	private SoundActions() {}

	public static void register(Registry r) {
		r.action("sound", SoundActions::sound);
		r.action("tune", SoundActions::tune);
		r.action("ambience", SoundActions::ambience);
		r.action("particles", SoundActions::particles);
	}

	// ---- sound ----

	private static Action sound(Params p, ShotContext shot) {
		String id = p.string("id");
		Place place = place(p, shot);
		float volume = (float) p.number("volume", 1), pitch = (float) p.number("pitch", 1);
		SoundSource category = category(p, place.relative ? "master" : "neutral");
		Identifier event = event(id, p, shot);
		return s -> {
			play(s, event, category, volume, pitch, place.at(s), place.relative);
			return true;
		};
	}

	// ---- tune ----

	private static Action tune(Params p, ShotContext shot) {
		Notes.Melody melody;
		try {
			melody = Notes.parse(p.string("notes"));
		} catch (IllegalArgumentException e) {
			throw new IllegalArgumentException(p.where() + ": " + e.getMessage());
		}
		List<BlockPos> blocks = new ArrayList<>();
		for (Vec3 v : positions(p, p.has("blocks") ? "blocks" : "block", shot)) blocks.add(BlockPos.containing(v));
		double bpm = p.number("bpm", 120), step = p.number("step", 0.5);
		if (bpm < 20 || bpm > 400) throw new IllegalArgumentException(p.where() + ": bpm is 20 to 400");
		if (step <= 0) throw new IllegalArgumentException(p.where() + ": step (beats per token) is > 0");
		NoteBlockInstrument fixed = p.has("instrument") ? instrument(p.string("instrument"), p) : null;
		float volume = (float) p.number("volume", 3);
		boolean particles = p.bool("particles", true);
		String mark = p.string("mark", null);
		double start = shot.seconds(), seconds = 60.0 / bpm * step;
		List<Notes.Note> notes = melody.notes();
		return new Action() {
			int next;

			@Override
			public boolean frame(ShotContext s) {
				Minecraft mc = s.minecraft();
				while (next < notes.size() && start + notes.get(next).step() * seconds <= s.seconds() + 1e-9) {
					Notes.Note n = notes.get(next);
					BlockPos pos = blocks.get(next % blocks.size());
					next++;
					NoteBlockInstrument instrument = fixed;
					BlockState state = mc.level == null ? null : mc.level.getBlockState(pos);
					if (instrument == null) instrument = state != null && state.hasProperty(NoteBlock.INSTRUMENT) ? state.getValue(NoteBlock.INSTRUMENT) : NoteBlockInstrument.HARP;
					Identifier event = instrument.getSoundEvent().value().location();
					float pitch = instrument.isTunable() ? Notes.pitch(n.value()) : 1f;
					play(s, event, SoundSource.RECORDS, volume, pitch, Vec3.atCenterOf(pos), false);
					if (mark != null && (next == 1 || notes.get(next - 2).step() != n.step())) s.mark(mark);
					// The block's own note particle, coloured by the note, as vanilla's NoteBlock.triggerEvent.
					if (particles && mc.level != null && instrument.isTunable())
						mc.level.addParticle(ParticleTypes.NOTE, pos.getX() + 0.5, pos.getY() + 1.2, pos.getZ() + 0.5, n.value() / 24.0, 0, 0);
				}
				return next >= notes.size();
			}
		};
	}

	private static NoteBlockInstrument instrument(String name, Params p) {
		for (NoteBlockInstrument i : NoteBlockInstrument.values()) if (i.getSerializedName().equals(name)) return i;
		List<String> names = new ArrayList<>();
		for (NoteBlockInstrument i : NoteBlockInstrument.values()) if (!i.hasCustomSound()) names.add(i.getSerializedName());
		throw new IllegalArgumentException(p.where() + ": no instrument '" + name + "'; known: " + String.join(", ", names));
	}

	// ---- ambience ----

	private static Action ambience(Params p, ShotContext shot) {
		String id = p.string("id");
		Identifier event = event(id, p, shot);
		Place place = place(p, shot);
		double every = p.number("every", 0.8), jitter = p.number("jitter", 0.5), spread = p.number("spread", place.relative ? 0 : 4);
		if (every < 0.05) throw new IllegalArgumentException(p.where() + ": every (mean seconds between sounds) is at least 0.05");
		float volume = (float) p.number("volume", 0.5), pitch = (float) p.number("pitch", 1), pitchJitter = (float) p.number("pitch_jitter", 0.1);
		SoundSource category = category(p, "ambient");
		double until = p.has("duration") ? shot.seconds() + p.number("duration") : Double.MAX_VALUE;
		Random random = new Random(SoundLog.seed() * 31 + p.where().hashCode() * 17L + shot.shot().hashCode());
		return new Action() {
			double next = shot.seconds() + every * random.nextDouble();

			@Override
			public boolean frame(ShotContext s) {
				if (s.seconds() >= until) return true;
				while (next <= s.seconds() + 1e-9) {
					Vec3 at = place.at(s);
					if (at != null && spread > 0) {
						double a = random.nextDouble() * Math.PI * 2, d = spread * Math.sqrt(random.nextDouble());
						at = at.add(Math.cos(a) * d, 0, Math.sin(a) * d);
					}
					float pj = pitch * (1 + pitchJitter * (float) (random.nextDouble() * 2 - 1));
					float vj = volume * (float) (0.75 + 0.25 * random.nextDouble());
					play(s, event, category, vj, pj, at, place.relative);
					next += every * Math.max(0.05, 1 + jitter * (random.nextDouble() * 2 - 1));
				}
				return false;
			}
		};
	}

	// ---- particles ----

	private static Action particles(Params p, ShotContext shot) {
		String id = p.string("id");
		Identifier key = Identifier.tryParse(id.contains(":") ? id : "minecraft:" + id);
		ParticleType<?> type = key == null ? null : BuiltInRegistries.PARTICLE_TYPE.getValue(key);
		if (!(type instanceof ParticleOptions options))
			throw new IllegalArgumentException(p.where() + ": '" + id + "' is not a simple particle (heart, note, happy_villager, cloud, poof, flame, smoke, crit, angry_villager, splash…)");
		Place place = place(p, shot);
		if (place.relative) throw new IllegalArgumentException(p.where() + ": particles need a place: pos or an actor");
		Vec3 offset = p.has("offset") ? vec(p.raw("offset").getAsJsonArray(), p.where() + ".offset") : Vec3.ZERO;
		int count = (int) p.number("count", 8);
		double[] spread = spread(p);
		double speed = p.number("speed", 0), every = p.number("every", 0);
		double until = shot.seconds() + p.number("duration", every > 0 ? shot.duration() : 0);
		Random random = new Random(SoundLog.seed() * 37 + p.where().hashCode() * 13L + shot.shot().hashCode());
		return new Action() {
			double next = shot.seconds();

			@Override
			public boolean frame(ShotContext s) {
				var level = s.minecraft().level;
				while (next <= s.seconds() + 1e-9) {
					Vec3 at = place.at(s);
					if (level != null && at != null) {
						at = at.add(offset);
						for (int i = 0; i < count; i++) {
							double x = at.x + spread[0] * (random.nextDouble() * 2 - 1), y = at.y + spread[1] * (random.nextDouble() * 2 - 1),
								z = at.z + spread[2] * (random.nextDouble() * 2 - 1);
							level.addParticle(options, x, y, z, speed * (random.nextDouble() * 2 - 1), speed * random.nextDouble(), speed * (random.nextDouble() * 2 - 1));
						}
					}
					if (every <= 0) return true;
					next += every;
				}
				return s.seconds() >= until;
			}
		};
	}

	private static double[] spread(Params p) {
		if (!p.has("spread")) return new double[] {0.4, 0.4, 0.4};
		JsonElement e = p.raw("spread");
		if (e.isJsonArray()) {
			Vec3 v = vec(e.getAsJsonArray(), p.where() + ".spread");
			return new double[] {v.x, v.y, v.z};
		}
		double d = e.getAsDouble();
		return new double[] {d, d, d};
	}

	// ---- shared ----

	/** Where a sound or burst is: {@code pos}, else {@code relative = true}, else the cue's actor (default the player). */
	private record Place(Vec3 fixed, String actor, boolean relative) {
		Vec3 at(ShotContext s) {
			if (relative) return null;
			if (fixed != null) return fixed;
			Entity e = s.actor(actor).entity();
			if (e == null) throw new IllegalStateException("actor '" + actor + "' is not in the world");
			return e.position();
		}
	}

	private static Place place(Params p, ShotContext shot) {
		if (p.has("pos")) return new Place(shot.position(p, "pos"), null, false);
		if (p.bool("relative", false)) return new Place(null, null, true);
		String actor = p.string("actor", "player");
		shot.actor(actor);
		return new Place(null, actor, false);
	}

	private static SoundSource category(Params p, String fallback) {
		String name = p.string("category", fallback);
		for (SoundSource s : SoundSource.values()) if (s.getName().equals(name)) return s;
		List<String> names = new ArrayList<>();
		for (SoundSource s : SoundSource.values()) names.add(s.getName());
		throw new IllegalArgumentException(p.where() + ": no sound category '" + name + "'; known: " + String.join(", ", names));
	}

	/** A sound event id, checked against the game's sounds (or the mix's own {@code videocraft:} events). */
	private static Identifier event(String id, Params p, ShotContext shot) {
		Identifier event = Identifier.tryParse(id.contains(":") ? id : "minecraft:" + id);
		if (event == null) throw new IllegalArgumentException(p.where() + ": '" + id + "' is not a sound id");
		if (event.getNamespace().equals("videocraft")) {
			// videocraft:lib/<name>: an original library sound; the compiler checked the name (cli/videocraft/audio/library).
			if (event.getPath().startsWith(Synth.LIBRARY) && event.getPath().length() > Synth.LIBRARY.length()) return event;
			if (!Synth.EVENTS.contains(event.getPath()))
				throw new IllegalArgumentException(p.where() + ": no synthesized sound '" + id + "'; known: videocraft:" + String.join(", videocraft:", Synth.EVENTS));
			return event;
		}
		if (shot.minecraft().getSoundManager().getSoundEvent(event) == null) {
			List<String> near = new ArrayList<>();
			String head = event.getPath().contains(".") ? event.getPath().substring(0, event.getPath().lastIndexOf('.')) : event.getPath();
			for (Identifier known : shot.minecraft().getSoundManager().getAvailableSounds())
				if (known.getPath().startsWith(head) && near.size() < 12) near.add(known.toString());
			throw new IllegalArgumentException(p.where() + ": no sound event '" + id + "'" + (near.isEmpty() ? "" : "; similar: " + String.join(", ", near)));
		}
		return event;
	}

	static void play(ShotContext s, Identifier event, SoundSource category, float volume, float pitch, Vec3 at, boolean relative) {
		if (event.getNamespace().equals("videocraft")) {
			SoundLog.synthetic(event.toString(), at, volume, pitch, relative);
			return;
		}
		Vec3 p = at == null ? Vec3.ZERO : at;
		s.minecraft().getSoundManager().play(new SimpleSoundInstance(event, category, volume, pitch, SoundLog.random(event), false, 0,
			relative ? SoundInstance.Attenuation.NONE : SoundInstance.Attenuation.LINEAR, p.x, p.y, p.z, relative));
	}

	private static List<Vec3> positions(Params p, String key, ShotContext shot) {
		JsonElement e = p.raw(key);
		if (e == null) throw new IllegalArgumentException(p.where() + ": missing 'blocks' (a list of note block positions) or 'block' (one)");
		List<Vec3> out = new ArrayList<>();
		if (e.isJsonArray() && !e.getAsJsonArray().isEmpty() && !e.getAsJsonArray().get(0).isJsonPrimitive()) {
			JsonArray list = e.getAsJsonArray();
			for (int i = 0; i < list.size(); i++) {
				JsonObject one = new JsonObject();
				one.add("p", list.get(i));
				out.add(shot.position(new Params(one, p.where() + "." + key + "[" + i + "]"), "p"));
			}
		} else {
			out.add(shot.position(p, key));
		}
		return out;
	}

	private static Vec3 vec(JsonArray a, String where) {
		if (a.size() != 3) throw new IllegalArgumentException(where + ": [x, y, z]");
		return new Vec3(a.get(0).getAsDouble(), a.get(1).getAsDouble(), a.get(2).getAsDouble());
	}
}
