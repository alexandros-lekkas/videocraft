package io.github.alexandroslekkas.videocraft.sound;

import io.github.alexandroslekkas.videocraft.VideocraftLog;
import io.github.alexandroslekkas.videocraft.api.ShotContext;
import io.github.alexandroslekkas.videocraft.director.Take;
import io.github.alexandroslekkas.videocraft.plan.Plan;
import net.minecraft.client.Minecraft;
import net.minecraft.client.resources.sounds.Sound;
import net.minecraft.client.resources.sounds.SoundInstance;
import net.minecraft.client.sounds.SoundEventListener;
import net.minecraft.client.sounds.WeighedSoundEvents;
import net.minecraft.resources.Identifier;
import net.minecraft.util.RandomSource;
import net.minecraft.world.phys.Vec3;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * The sound log: every sound the client starts while a shot is prepared or recorded, one row of
 * {@code shots/<name>/sounds.csv} each. The game is muted, so this log is the sound track: the edit rebuilds it from the
 * user's own game assets ({@code cli/videocraft/audio/}).
 *
 * <p>Rows come from a {@link SoundEventListener} on the sound manager. Vanilla notifies listeners after it has resolved
 * the variant (so {@code file} is the one actually chosen) and <em>before</em> it drops a sound whose volume is zero,
 * so master volume 0 does not hide anything. {@code frame} is the shot's frame: sounds started while the shot was
 * still being prepared get a negative frame (only the last {@link #PREP_SECONDS} seconds are kept) and the mix decides
 * whether they still sound at frame 0. Events in the {@code videocraft:} namespace are not game sounds: actions log
 * them directly ({@link #synthetic}) and the mix synthesizes them.
 *
 * <p>Determinism: before vanilla resolves a sound, {@code SoundEngineMixin} gives the instance a random source seeded
 * from the take seed, the shot, the frame and the order within the frame ({@link #random}), so the variant and any
 * sampled volume or pitch are the same in every take of the plan.
 *
 * <p>Hooks (in {@code director/ShotRun}): {@link #frame} at the top of each frame of a shot, {@link #write} when the shot
 * ends. Everything here runs on the render thread.
 */
public final class SoundLog {
	public static final String HEADER = "frame,event,file,category,volume,pitch,x,y,z,relative,attenuation_distance,looping\n";
	static final double PREP_SECONDS = 20;

	private record Row(int abs, int frame, boolean known, String event, String file, String category, float volume, float pitch,
		double x, double y, double z, boolean relative, float range, boolean looping) {}

	private static final SoundEventListener LISTENER = SoundLog::onPlay;
	private static boolean installed;
	private static ShotContext shot;
	private static int abs, seq, offset;
	private static boolean offsetKnown;
	private static final List<Row> rows = new ArrayList<>();
	private static Long takeSeed;

	private SoundLog() {}

	/** Hook: once per frame of a shot (prepared or recorded), before its actions run. */
	public static void frame(ShotContext s) {
		if (!installed) {
			Minecraft.getInstance().getSoundManager().addListener(LISTENER);
			installed = true;
		}
		if (s != shot) {
			shot = s;
			rows.clear();
			abs = 0;
			offsetKnown = false;
		}
		abs++;
		seq = 0;
	}

	/** Whether a filmed shot is being prepared or recorded (staging is not logged). */
	public static boolean active() {
		return shot != null && !"stage".equals(shot.shot());
	}

	/** A random source for the next sound that starts this frame: the same in every take of this plan. */
	public static RandomSource random(Identifier id) {
		long h = seed() * 0x9E3779B97F4A7C15L;
		h ^= (shot == null ? 0 : shot.shot().hashCode()) * 0xC2B2AE3D27D4EB4FL;
		// The shot's own frame index, not the frames since it began preparing: preparation takes longer in one take than another.
		h ^= ((long) (shot == null ? abs : shot.frame()) << 20) ^ (seq++ * 0x165667B19E3779F9L) ^ id.hashCode();
		return RandomSource.create(h);
	}

	/** The take's seed (from plan.json), for actions that want their own seeded randomness. */
	public static long seed() {
		if (takeSeed == null) {
			long s = 1;
			try {
				Take take = Take.fromSystemProperty();
				if (take != null) s = Plan.read(take.plan()).seed();
			} catch (Exception e) {
				VideocraftLog.LOGGER.warn("VIDEOCRAFT sound log could not read the take seed: {}", e.toString());
			}
			takeSeed = s;
		}
		return takeSeed;
	}

	private static void onPlay(SoundInstance instance, WeighedSoundEvents events, float range) {
		if (!active()) return;
		Sound sound = instance.getSound();
		String file = sound == null ? "" : strip(sound.getLocation());
		add(instance.getIdentifier().toString(), file, instance.getSource().getName(), instance.getVolume(), instance.getPitch(),
			instance.getX(), instance.getY(), instance.getZ(), instance.isRelative() || instance.getAttenuation() == SoundInstance.Attenuation.NONE,
			range, instance.isLooping());
	}

	/** Logs an event the game has no sound for ({@code videocraft:kick}, {@code videocraft:cricket}…): the mix makes it. */
	public static void synthetic(String event, Vec3 at, float volume, float pitch, boolean relative) {
		if (!active()) return;
		Vec3 p = at == null ? Vec3.ZERO : at;
		add(event, "", "master", volume, pitch, p.x, p.y, p.z, relative || at == null, 16 * Math.max(1, volume), false);
	}

	private static void add(String event, String file, String category, float volume, float pitch, double x, double y, double z,
		boolean relative, float range, boolean looping) {
		boolean known = shot.recording();
		int frame = known ? shot.frame() : 0;
		if (known && !offsetKnown) {
			offset = abs - frame;
			offsetKnown = true;
		}
		rows.add(new Row(abs, frame, known, event, file, category, volume, pitch, x, y, z, relative, range, looping));
	}

	/** Hook: the shot ended; writes {@code sounds.csv} into the shot's folder. */
	public static void write(ShotContext s, Path dir) {
		if (s != shot) {
			// Nothing was played in this shot's frames (or the hook order changed): an empty log is still a log.
			rows.clear();
			shot = s;
		}
		int base = offsetKnown ? offset : abs - s.frame();
		int earliest = (int) -Math.round(PREP_SECONDS * s.fps());
		StringBuilder out = new StringBuilder(HEADER);
		int logged = 0;
		for (Row r : rows) {
			int frame = r.known ? r.frame : r.abs - base;
			if (frame < earliest) continue;
			out.append(String.format(Locale.ROOT, "%d,%s,%s,%s,%.4f,%.4f,%.4f,%.4f,%.4f,%d,%.2f,%d%n", frame, r.event, r.file, r.category,
				r.volume, r.pitch, r.x, r.y, r.z, r.relative ? 1 : 0, r.range, r.looping ? 1 : 0));
			logged++;
		}
		try {
			Files.writeString(dir.resolve("sounds.csv"), out, StandardCharsets.UTF_8);
		} catch (IOException e) {
			VideocraftLog.LOGGER.warn("VIDEOCRAFT could not write the sound log of {}", s.shot(), e);
		}
		VideocraftLog.LOGGER.info("VIDEOCRAFT {} sounds logged: {}", s.shot(), logged);
		rows.clear();
		shot = null;
	}

	private static String strip(Identifier id) {
		return "minecraft".equals(id.getNamespace()) ? id.getPath() : id.toString();
	}
}
