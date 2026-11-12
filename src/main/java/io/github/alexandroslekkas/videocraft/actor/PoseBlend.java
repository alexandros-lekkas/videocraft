package io.github.alexandroslekkas.videocraft.actor;

import net.minecraft.client.model.Model;
import net.minecraft.client.model.animal.parrot.ParrotModel;
import net.minecraft.client.model.geom.ModelPart;
import net.minecraft.client.renderer.entity.state.BeeRenderState;
import net.minecraft.client.renderer.entity.state.FelineRenderState;
import net.minecraft.client.renderer.entity.state.FoxRenderState;
import net.minecraft.client.renderer.entity.state.HumanoidRenderState;
import net.minecraft.client.renderer.entity.state.ParrotRenderState;
import net.minecraft.client.renderer.entity.state.WolfRenderState;

import java.util.List;
import java.util.function.Consumer;

/**
 * Eases a puppet's model between two of vanilla's on/off poses. A fox sits, a fox lies down to sleep, a wolf or a cat
 * sits, a mannequin sits or crouches, a bee or a parrot lands or takes off: vanilla switches each in a single frame (its model reads a boolean), which on
 * screen is a pop. While such a state has just changed ({@link Puppet#shift()}), the model is posed twice, once with
 * the old value and once with the new, and every part is drawn in between by the eased progress of the change. Poses
 * vanilla already eases (a fox's crouch, a goat lowering its head, a cat lying down) are left alone. Render thread.
 */
public final class PoseBlend {
	private PoseBlend() {}

	/** Poses {@code model} for {@code state} through {@code setupAnim} (vanilla's), blended while a state changes. */
	public static void setup(Model<?> model, Object state, Consumer<Object> setupAnim) {
		Puppet p = state instanceof PuppetState ps ? ps.videocraft$puppet() : null;
		Puppet.Shift shift = p == null ? null : p.shift();
		Boolean now = shift == null ? null : get(state, shift.flag());
		if (now == null) {
			setupAnim.accept(state);
			return;
		}
		List<ModelPart> parts = model.allParts();
		float[] was = new float[parts.size() * 9];
		set(state, shift.flag(), !now);
		setupAnim.accept(state);
		for (int i = 0; i < parts.size(); i++) store(parts.get(i), was, i * 9);
		set(state, shift.flag(), now);
		setupAnim.accept(state);
		float w = (float) shift.weight();
		for (int i = 0; i < parts.size(); i++) mix(parts.get(i), was, i * 9, w);
	}

	/** The render state's flag for a puppet state, or null where this body has none to blend. */
	static Boolean get(Object s, String flag) {
		return switch (flag) {
			case "sit" -> s instanceof FoxRenderState f ? f.isSitting : s instanceof FelineRenderState c ? c.isSitting
				: s instanceof WolfRenderState w ? w.isSitting : s instanceof HumanoidRenderState h ? h.isPassenger : null;
			case "sleep" -> s instanceof FoxRenderState f ? f.isSleeping : null;
			case "crouch" -> s instanceof HumanoidRenderState h ? h.isCrouching : null;
			// A flyer landing or taking off: a bee's wings stop beating and its legs fold; a parrot folds its wings.
			case "ground" -> s instanceof BeeRenderState b ? b.isOnGround
				: s instanceof ParrotRenderState pr && (pr.pose == ParrotModel.Pose.FLYING || pr.pose == ParrotModel.Pose.STANDING) ? pr.pose == ParrotModel.Pose.STANDING : null;
			default -> null;
		};
	}

	private static void set(Object s, String flag, boolean on) {
		switch (flag) {
			case "sit" -> {
				if (s instanceof FoxRenderState f) f.isSitting = on;
				else if (s instanceof FelineRenderState c) c.isSitting = on;
				else if (s instanceof WolfRenderState w) w.isSitting = on;
				else if (s instanceof HumanoidRenderState h) h.isPassenger = on;
			}
			case "sleep" -> { if (s instanceof FoxRenderState f) f.isSleeping = on; }
			case "crouch" -> { if (s instanceof HumanoidRenderState h) h.isCrouching = on; }
			case "ground" -> {
				if (s instanceof BeeRenderState b) b.isOnGround = on;
				else if (s instanceof ParrotRenderState pr) pr.pose = on ? ParrotModel.Pose.STANDING : ParrotModel.Pose.FLYING;
			}
			default -> {}
		}
	}

	private static void store(ModelPart p, float[] a, int o) {
		a[o] = p.x; a[o + 1] = p.y; a[o + 2] = p.z;
		a[o + 3] = p.xRot; a[o + 4] = p.yRot; a[o + 5] = p.zRot;
		a[o + 6] = p.xScale; a[o + 7] = p.yScale; a[o + 8] = p.zScale;
	}

	private static void mix(ModelPart p, float[] a, int o, float w) {
		p.x = a[o] + (p.x - a[o]) * w;
		p.y = a[o + 1] + (p.y - a[o + 1]) * w;
		p.z = a[o + 2] + (p.z - a[o + 2]) * w;
		p.xRot = a[o + 3] + (p.xRot - a[o + 3]) * w;
		p.yRot = a[o + 4] + (p.yRot - a[o + 4]) * w;
		p.zRot = a[o + 5] + (p.zRot - a[o + 5]) * w;
		p.xScale = a[o + 6] + (p.xScale - a[o + 6]) * w;
		p.yScale = a[o + 7] + (p.yScale - a[o + 7]) * w;
		p.zScale = a[o + 8] + (p.zScale - a[o + 8]) * w;
	}
}
