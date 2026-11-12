package io.github.alexandroslekkas.videocraft;

import io.github.alexandroslekkas.videocraft.sound.Notes;
import io.github.alexandroslekkas.videocraft.sound.SoundLog;

/** The audio workstream's plain-JVM checks: the note block melody parser and the sound log's columns. */
public final class SoundChecks {
	public static void main(String[] args) {
		// Note names are at harp pitch: F#3 is note value 0, F#4 is 12, F#5 is 24.
		PlanChecks.check(Notes.value("f#3") == 0 && Notes.value("f#4") == 12 && Notes.value("f#5") == 24, "note names map to note block values");
		PlanChecks.check(Notes.value("c4") == 6 && Notes.value("bb4") == 16 && Notes.value("7") == 7, "flats and bare values");
		PlanChecks.check(Math.abs(Notes.pitch(12) - 1f) < 1e-6 && Math.abs(Notes.pitch(24) - 2f) < 1e-6 && Math.abs(Notes.pitch(0) - 0.5f) < 1e-6, "pitch is 2^((n-12)/12)");
		Notes.Melody m = Notes.parse("c4 e4 - g4*2 c4+e4");
		PlanChecks.check(m.steps() == 6 && m.notes().size() == 5, "steps and notes: " + m);
		PlanChecks.check(m.notes().get(2).step() == 3 && m.notes().get(3).step() == 5 && m.notes().get(4).step() == 5, "rests, holds and chords take their steps: " + m);
		for (String bad : new String[] {"c6", "e3", "h4", "c4*0", "-"}) {
			boolean threw = false;
			try { Notes.parse(bad); } catch (IllegalArgumentException e) { threw = true; }
			PlanChecks.check(threw, "rejects '" + bad + "'");
		}
		// The columns are a contract with cli/videocraft/audio (add at the end only).
		PlanChecks.check(SoundLog.HEADER.equals("frame,event,file,category,volume,pitch,x,y,z,relative,attenuation_distance,looping\n"), "sounds.csv header");
		System.out.println("SoundChecks PASS");
	}
}
