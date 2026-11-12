package dev.blockreel;

import com.google.gson.JsonParser;
import dev.blockreel.plan.Plan;

import java.nio.file.Files;
import java.nio.file.Path;

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
		System.out.println("PlanChecks PASS " + checked + " plans");
	}

	static void check(boolean ok, String what) {
		if (!ok) throw new AssertionError(what);
	}
}
