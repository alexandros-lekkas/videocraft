package io.github.alexandroslekkas.videocraft.director;

import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * The take directory the CLI hands the mod ({@code -Dvideocraft.take=<dir>}): it reads {@code plan.json} there and
 * writes everything else. Layout (docs/DESIGN.md, "Run store"):
 * <pre>
 * plan.json                     in: the compiled script
 * result.json                   out: verdict, reason, per-shot frame counts and sizes, timings
 * shots/&lt;name&gt;/video.mp4      out: the shot as captured, 1 frame per fixed step
 * shots/&lt;name&gt;/frames.csv     out: camera and player per captured frame
 * shots/&lt;name&gt;/marks.json     out: beats noted by actions, in frames of this shot
 * shots/&lt;name&gt;/ffmpeg.log
 * </pre>
 */
public record Take(Path dir) {
	public static Take fromSystemProperty() {
		String dir = System.getProperty("videocraft.take");
		return dir == null || dir.isBlank() ? null : new Take(Path.of(dir).toAbsolutePath());
	}

	public Path plan() { return dir.resolve("plan.json"); }

	public Path shot(String name) {
		Path path = dir.resolve("shots").resolve(name);
		try { Files.createDirectories(path); } catch (IOException e) { throw new UncheckedIOException(e); }
		return path;
	}

	public void writeResult(JsonObject result) {
		try {
			Path tmp = dir.resolve("result.json.part");
			Files.writeString(tmp, new GsonBuilder().setPrettyPrinting().create().toJson(result) + "\n", StandardCharsets.UTF_8);
			Files.move(tmp, dir.resolve("result.json"), java.nio.file.StandardCopyOption.REPLACE_EXISTING, java.nio.file.StandardCopyOption.ATOMIC_MOVE);
		} catch (IOException e) {
			throw new UncheckedIOException(e);
		}
	}
}
