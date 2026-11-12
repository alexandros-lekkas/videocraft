package dev.blockreel.director;

import com.google.gson.JsonObject;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import dev.blockreel.BlockreelLog;
import net.minecraft.client.Minecraft;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

/**
 * The loopback control port ({@code -Dblockreel.port}, default 25750): how the CLI asks a running take how far it is
 * and stops it cleanly. JSON over HTTP on 127.0.0.1 only; requests whose Host is not loopback (DNS rebinding) or that
 * carry an Origin (a browser) are refused. Endpoints: {@code GET /status}, {@code POST /quit}. More (submit a plan to a
 * warm client, run a command) belong to workstream (a); see docs/DESIGN.md.
 */
public final class ControlServer {
	private ControlServer() {}

	public static void start(int port) {
		try {
			HttpServer server = HttpServer.create(new InetSocketAddress(InetAddress.getLoopbackAddress(), port), 8);
			server.createContext("/status", ex -> handle(ex, "GET", () -> {
				Director d = Director.current();
				if (d != null) return d.status();
				JsonObject o = new JsonObject();
				o.addProperty("step", "IDLE");
				return o;
			}));
			server.createContext("/quit", ex -> handle(ex, "POST", () -> {
				Minecraft mc = Minecraft.getInstance();
				mc.execute(mc::stop);
				JsonObject o = new JsonObject();
				o.addProperty("ok", true);
				return o;
			}));
			server.setExecutor(null);
			server.start();
			// Its dispatcher thread is not a daemon: stop it with the client, or the JVM outlives the game and the
			// shutdown watchdog reports a crash.
			net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents.CLIENT_STOPPING.register(client -> server.stop(0));
			BlockreelLog.LOGGER.info("BLOCKREEL control on http://127.0.0.1:{}", port);
		} catch (IOException e) {
			BlockreelLog.LOGGER.warn("BLOCKREEL control port {} unavailable: {}", port, e.toString());
		}
	}

	private static void handle(HttpExchange ex, String method, java.util.function.Supplier<JsonObject> body) throws IOException {
		String host = ex.getRequestHeaders().getFirst("Host");
		boolean loopback = host != null && (host.startsWith("127.0.0.1:") || host.startsWith("localhost:"));
		int code;
		String text;
		if (!loopback || ex.getRequestHeaders().containsKey("Origin")) { code = 403; text = "{\"error\":\"loopback clients only\"}"; }
		else if (!ex.getRequestMethod().equals(method)) { code = 405; text = "{\"error\":\"use " + method + "\"}"; }
		else { code = 200; text = body.get().toString(); }
		byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
		ex.getResponseHeaders().set("Content-Type", "application/json");
		ex.sendResponseHeaders(code, bytes.length);
		try (var out = ex.getResponseBody()) { out.write(bytes); }
	}
}
