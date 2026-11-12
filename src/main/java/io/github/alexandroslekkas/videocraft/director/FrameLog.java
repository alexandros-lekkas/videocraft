package io.github.alexandroslekkas.videocraft.director;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Locale;

/**
 * frames.csv of one shot: one row per captured frame, what the camera and the player were. The measure step reads it
 * (camera jerk, view speed, whether the subject is in the safe area), so the columns are a contract: add, never rename.
 */
final class FrameLog {
	static final String HEADER = "frame,seconds,cam_x,cam_y,cam_z,cam_yaw,cam_pitch,fov,player_x,player_y,player_z,player_yaw,player_pitch,on_ground,subject,subject_x,subject_y,subject_z,subject_yaw,subject_head_y,lens_fov\n";
	private final StringBuilder rows = new StringBuilder(HEADER);
	private int last = -1;

	/** {@code subject} is {x, y, z, yaw, head y} of the rig's subject, or null (empty columns). */
	void row(int frame, double seconds, double[] cam, double fov, double[] player, boolean onGround, String subjectId, double[] subject) {
		if (frame <= last) return;
		last = frame;
		rows.append(String.format(Locale.ROOT, "%d,%.4f,%.4f,%.4f,%.4f,%.3f,%.3f,%d,%.4f,%.4f,%.4f,%.3f,%.3f,%d,", frame, seconds,
			cam[0], cam[1], cam[2], cam[3], cam[4], Math.round(fov), player[0], player[1], player[2], player[3], player[4], onGround ? 1 : 0));
		if (subject == null) rows.append(",,,,,,");
		else rows.append(String.format(Locale.ROOT, "%s,%.4f,%.4f,%.4f,%.3f,%.4f,", subjectId, subject[0], subject[1], subject[2], subject[3], subject[4]));
		rows.append(String.format(Locale.ROOT, "%.3f%n", fov));
	}

	void write(Path file) throws IOException {
		Files.writeString(file, rows, StandardCharsets.UTF_8);
	}
}
