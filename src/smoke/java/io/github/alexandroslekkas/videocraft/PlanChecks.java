package io.github.alexandroslekkas.videocraft;

import com.google.gson.JsonParser;
import io.github.alexandroslekkas.videocraft.api.ActionType;
import io.github.alexandroslekkas.videocraft.api.Registry;
import io.github.alexandroslekkas.videocraft.api.RigType;
import io.github.alexandroslekkas.videocraft.camera.Rigs;
import io.github.alexandroslekkas.videocraft.director.PlanCheck;
import io.github.alexandroslekkas.videocraft.plan.Plan;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/** plan.json parsing without Minecraft: the shape the CLI compiles (cli/tests/plans/*.json) is the shape the mod reads. */
public final class PlanChecks {
	public static void main(String[] args) throws Exception {
		int checked = 0;
		try (var files = Files.list(Path.of("cli/tests/plans"))) {
			for (Path file : files.filter(f -> f.toString().endsWith(".plan.json")).sorted().toList()) {
				Plan plan = Plan.parse(JsonParser.parseString(Files.readString(file)).getAsJsonObject());
				check(!plan.shots().isEmpty(), file + ": no shots");
				check(plan.output().fps() > 0, file + ": fps");
				for (Plan.Shot shot : plan.shots()) check(shot.camera().has("rig"), file + ": shot " + shot.name() + " has no rig");
				checked++;
			}
		}
		check(checked > 0, "no plans in cli/tests/plans");
		boolean refused = false;
		try {
			Plan.parse(JsonParser.parseString("{\"version\": 99}").getAsJsonObject());
		} catch (IllegalArgumentException e) {
			refused = e.getMessage().contains("version 99");
		}
		check(refused, "a plan of another version is refused by name");
		checkBeforeTheWorld();
		System.out.println("PlanChecks PASS " + checked + " plans");
	}

	/** PlanCheck finds every mistake of a plan without a world, each naming its shot and cue. */
	static void checkBeforeTheWorld() {
		Map<String, RigType> rigs = new HashMap<>();
		Map<String, ActionType> actions = new HashMap<>();
		Rigs.register(new Registry() {
			@Override public void action(String id, ActionType type) {}
			@Override public void rig(String id, RigType type) { rigs.put("videocraft:" + id, type); }
		});
		actions.put("videocraft:mark", (p, shot) -> { p.string("label"); return s -> true; });
		actions.put("videocraft:stand_in", (p, shot) -> { throw new NullPointerException("needs a level"); });
		actions.put("videocraft:glide", (p, shot) -> s -> true);
		java.util.function.Function<String, RigType> rig = n -> {
			RigType t = rigs.get(n.contains(":") ? n : "videocraft:" + n);
			if (t == null) throw new IllegalArgumentException("no camera rig '" + n + "'");
			return t;
		};
		java.util.function.Function<String, ActionType> action = n -> {
			ActionType t = actions.get(n.contains(":") ? n : "videocraft:" + n);
			if (t == null) throw new IllegalArgumentException("no action '" + n + "'");
			return t;
		};
		String plan = """
			{"version": 1, "name": "bad", "seed": 1, "output": {"width": 1920, "height": 1080, "fps": 60},
			 "world": {"seed": "1", "gamemode": "creative", "time": 6000, "weather": "clear", "settle": 1,
			   "stage": [{"at": 0, "do": "stand_in", "id": "dummy", "place": [0, 64, 0]}]},
			 "actors": [],
			 "shots": [
			  {"name": "good", "duration": 2, "preroll": 1, "camera": {"rig": "lead", "subject": "dummy"},
			   "timeline": [{"at": -1, "do": "glide", "actor": "dummy", "path": [[0, 64, 0], [0, 64, 5]]}, {"at": 1, "do": "mark", "label": "x"}]},
			  {"name": "a", "duration": 2, "camera": {"rig": "dolley"}, "timeline": [{"at": 3, "do": "mark", "label": "late"}]},
			  {"name": "b", "duration": 2, "camera": {"rig": "lead", "subject": "nibs"}, "timeline": [{"at": 0, "do": "wlak"}]},
			  {"name": "c", "duration": 2, "camera": {"rig": "face", "subject": "dummy", "fov": 150},
			   "timeline": [{"at": 0, "do": "glide", "actor": "player"}, {"at": 0, "do": "mark"}]},
			  {"name": "d", "duration": 2, "camera": {"rig": "fixed", "eye": {"actor": "duke"}, "at": [0, 64, 0]}}]}
			""";
		List<String> problems = PlanCheck.problems(Plan.parse(JsonParser.parseString(plan).getAsJsonObject()), action, rig, null);
		String[] expected = {"shots.a.camera: no camera rig 'dolley'", "shots.a.timeline[0]: at 3.0 is outside", "shots.b.camera: no actor 'nibs'",
			"shots.b.timeline[0]: no action 'wlak'", "shots.c.camera: fov is", "shots.c.timeline[0]: glide moves a stand_in", "shots.c.timeline[1]: missing 'label'",
			"shots.d.camera.eye: no actor 'duke'"};
		check(problems.size() == expected.length, "PlanCheck finds " + expected.length + " problems, not " + problems.size() + ": " + problems);
		for (int i = 0; i < expected.length; i++) check(problems.get(i).contains(expected[i]), "PlanCheck problem " + i + " is '" + expected[i] + "', got: " + problems.get(i));
	}

	static void check(boolean ok, String what) {
		if (!ok) throw new AssertionError(what);
	}
}
