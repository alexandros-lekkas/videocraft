package io.github.alexandroslekkas.videocraft.director;

import com.mojang.blaze3d.pipeline.RenderTarget;
import com.mojang.blaze3d.platform.NativeImage;
import io.github.alexandroslekkas.videocraft.VideocraftLog;
import net.minecraft.client.Screenshot;

import java.io.File;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.Channels;
import java.nio.channels.WritableByteChannel;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Frames straight from the game's framebuffer into one ffmpeg child per shot. {@link #grab} is called once per frame
 * before the clock advances, so it reads the frame rendered last; the GPU readback is asynchronous and the encoder
 * runs on its own thread. The queue is small and {@code put} blocks, so a slow encoder slows the game rather than
 * dropping frames; the fixed clock keeps the video steady regardless. Ported from T3 Craft's DemoRecorder.
 */
public final class Capture {
	private record Frame(Segment segment, NativeImage image) {}

	private final String ffmpeg;
	private final BlockingQueue<Frame> queue = new ArrayBlockingQueue<>(6);
	private final List<Segment> segments = new CopyOnWriteArrayList<>();
	private volatile Segment open;
	private volatile String error;

	public Capture(String ffmpeg) {
		this.ffmpeg = ffmpeg;
		Thread writer = new Thread(this::write, "videocraft-encoder");
		writer.setDaemon(true);
		writer.start();
	}

	/** One shot's video: started on its first frame, when the frame size is known. */
	public static final class Segment {
		public final String name;
		final Path dir;
		final int fps;
		final AtomicInteger pending = new AtomicInteger();
		volatile int requested, written, width, height, exit = -1;
		volatile boolean ended, closeQueued, done;
		private Process process;
		private WritableByteChannel channel;

		Segment(String name, Path dir, int fps) {
			this.name = name;
			this.dir = dir;
			this.fps = fps;
		}

		public int frames() { return written; }
		public int width() { return width; }
		public int height() { return height; }
		public int exitCode() { return exit; }
		public Path video() { return dir.resolve("video.mp4"); }
	}

	public Segment begin(String name, Path dir, int fps) {
		end();
		Segment s = new Segment(name, dir, fps);
		segments.add(s);
		open = s;
		return s;
	}

	public void end() {
		Segment s = open;
		if (s == null) return;
		open = null;
		s.ended = true;
	}

	public boolean recording() { return open != null; }

	/** Every segment is closed and its encoder has exited. */
	public boolean idle() { return open == null && segments.stream().allMatch(s -> s.done); }

	public String error() { return error; }

	public List<Segment> segments() { return List.copyOf(segments); }

	/** Asks for the frame just rendered (if a shot is recording) and closes segments whose last frame has been read. */
	public void grab(RenderTarget target) {
		Segment s = open;
		if (s != null) {
			s.requested++;
			s.pending.incrementAndGet();
			Screenshot.takeScreenshot(target, image -> {
				try { queue.put(new Frame(s, image)); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
				s.pending.decrementAndGet();
			});
		}
		for (Segment closing : segments) {
			if (closing.ended && !closing.closeQueued && closing.pending.get() == 0) {
				closing.closeQueued = true;
				try { queue.put(new Frame(closing, null)); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
			}
		}
	}

	private void write() {
		while (true) {
			Frame f;
			try { f = queue.take(); } catch (InterruptedException e) { return; }
			try {
				if (f.image == null) finish(f.segment);
				else try { encode(f.segment, f.image); } finally { f.image.close(); }
			} catch (Exception e) {
				error = "encoder: " + e;
				VideocraftLog.LOGGER.error("VIDEOCRAFT encoder failed on {}", f.segment.name, e);
				f.segment.done = true;
			}
		}
	}

	private void encode(Segment s, NativeImage image) throws IOException {
		int w = image.getWidth(), h = image.getHeight();
		if (s.process == null) {
			s.width = w;
			s.height = h;
			File log = s.dir.resolve("ffmpeg.log").toFile();
			// Near-lossless intermediate: the cut re-encodes once at the end. BT.709 tagged, so players show the game's colours.
			s.process = new ProcessBuilder(ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgba", "-s", w + "x" + h, "-r", String.valueOf(s.fps),
				"-i", "-", "-an", "-vf", "scale=out_color_matrix=bt709:out_range=tv", "-c:v", "libx264", "-preset", "veryfast", "-crf", "12", "-pix_fmt", "yuv420p",
				"-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", s.video().toString())
				.redirectErrorStream(true).redirectOutput(log).start();
			s.channel = Channels.newChannel(s.process.getOutputStream());
			VideocraftLog.LOGGER.info("VIDEOCRAFT shot {} recording at {}x{} {} fps", s.name, w, h, s.fps);
		}
		if (w != s.width || h != s.height) throw new IOException("frame size changed mid-shot: " + s.width + "x" + s.height + " -> " + w + "x" + h);
		ByteBuffer pixels = org.lwjgl.system.MemoryUtil.memByteBuffer(image.getPointer(), w * h * 4);
		while (pixels.hasRemaining()) s.channel.write(pixels);
		s.written++;
	}

	private void finish(Segment s) throws IOException, InterruptedException {
		if (s.process != null) {
			s.channel.close();
			s.exit = s.process.waitFor();
			VideocraftLog.LOGGER.info("VIDEOCRAFT shot {} closed: {} frames, ffmpeg exit {}", s.name, s.written, s.exit);
		} else {
			s.exit = 0;
		}
		s.done = true;
	}
}
