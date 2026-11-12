package io.github.alexandroslekkas.videocraft.actor;

import com.mojang.brigadier.exceptions.CommandSyntaxException;
import io.github.alexandroslekkas.videocraft.api.Params;
import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.TagParser;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.TamableAnimal;
import net.minecraft.world.entity.animal.feline.Cat;
import net.minecraft.world.entity.animal.fox.Fox;
import net.minecraft.world.entity.animal.goat.Goat;
import net.minecraft.world.entity.decoration.Mannequin;
import net.minecraft.world.item.DyeColor;

import java.util.Locale;

/**
 * An actor's look from the script, mapped to the entity's own saved data (what {@code /summon} would take), so every
 * option is the game's real state: {@code variant} (a fox's {@code snow}, a cat's {@code black}, a chicken's {@code
 * cold}...), a goat's {@code left_horn}/{@code right_horn}/{@code screaming}, {@code baby}, a sheep's {@code color},
 * a mannequin's {@code skin}, and {@code nbt} for anything else. The name tag is off unless {@code show_name}.
 */
final class Looks {
	private Looks() {}

	static CompoundTag tag(Puppet p, Params spec) {
		CompoundTag tag = new CompoundTag();
		String entity = p.entityId;
		if (spec.has("variant")) {
			String v = spec.string("variant");
			if (entity.equals("minecraft:fox")) {
				if (!v.equals("red") && !v.equals("snow")) throw new IllegalArgumentException(spec.where() + ": a fox's variant is red or snow, not '" + v + "'");
				tag.putString("Type", v);
			} else {
				tag.putString("variant", v.contains(":") ? v : "minecraft:" + v);
			}
		}
		if (spec.has("left_horn")) tag.putBoolean("HasLeftHorn", spec.bool("left_horn", true));
		if (spec.has("right_horn")) tag.putBoolean("HasRightHorn", spec.bool("right_horn", true));
		if (spec.has("screaming")) tag.putBoolean("IsScreamingGoat", spec.bool("screaming", false));
		if (spec.bool("baby", false)) { tag.putInt("Age", -24000); tag.putBoolean("AgeLocked", true); tag.putBoolean("IsBaby", true); }
		if (spec.has("color")) {
			DyeColor color = DyeColor.byName(spec.string("color"), null);
			if (color == null) throw new IllegalArgumentException(spec.where() + ": color is a dye colour (white, light_blue, ...), not '" + spec.string("color") + "'");
			tag.putByte("Color", (byte) color.getId());
		}
		if (p.kind.equals("mannequin")) {
			tag.put("profile", Skins.profileTag(p.id, spec));
			tag.putBoolean("hide_description", true);
			tag.putBoolean("immovable", true);
		}
		if (spec.has("nbt")) {
			try {
				tag.merge(TagParser.parseCompoundFully(spec.string("nbt")));
			} catch (CommandSyntaxException e) {
				throw new IllegalArgumentException(spec.where() + ".nbt: " + e.getMessage());
			}
		}
		return tag;
	}

	/** After loading: a name tag only when asked, and the entity's own states the script starts in. */
	static void after(Puppet p, LivingEntity e, Params spec) {
		if (spec.has("name")) {
			e.setCustomName(Component.literal(spec.string("name")));
			e.setCustomNameVisible(spec.bool("show_name", false));
		}
		if (!spec.bool("show_name", false)) e.setCustomNameVisible(false);
		for (String s : spec.strings("states")) p.state(s, true, spec.where() + ".states");
	}

	/** {@code wool = "#rrggbb"} → a sheep's wool colour beyond the sixteen dyes (ARGB), or -1 (its dye's). */
	static int wool(Params spec) {
		if (!spec.has("wool")) return -1;
		String t = spec.string("wool").trim();
		if (!t.matches("#[0-9a-fA-F]{6}")) throw new IllegalArgumentException(spec.where() + ": wool is \"#rrggbb\", not '" + t + "'");
		return 0xFF000000 | Integer.parseInt(t.substring(1), 16);
	}

	/** {@code tint = "#rrggbb"} → an ARGB multiplier for the model, or -1 (none). */
	static int tint(Params spec) {
		if (!spec.has("tint")) return -1;
		String t = spec.string("tint").trim();
		if (!t.matches("#[0-9a-fA-F]{6}")) throw new IllegalArgumentException(spec.where() + ": tint is \"#rrggbb\", not '" + t + "'");
		return 0xFF000000 | Integer.parseInt(t.substring(1), 16);
	}

	/** The states an entity has, for error messages. */
	static String states(LivingEntity e) {
		if (e instanceof Fox) return "sit, sleep, crouch (a bow), pounce, tilt, faceplant, flap";
		if (e instanceof Goat) return "lower (as if to ram), crouch, flap";
		if (e instanceof Cat) return "sit, lie, flap";
		if (e instanceof TamableAnimal) return "sit, flap";
		if (e instanceof Mannequin) return "sit, sleep, crouch";
		return "flap" + (e == null ? "" : " (" + e.getType().toShortString().toLowerCase(Locale.ROOT) + " has no poses of its own)");
	}
}
