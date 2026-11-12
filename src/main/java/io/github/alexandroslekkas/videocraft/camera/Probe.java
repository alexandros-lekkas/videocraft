package io.github.alexandroslekkas.videocraft.camera;

import net.minecraft.client.Minecraft;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.phys.shapes.CollisionContext;

/**
 * Whether the camera can be somewhere: how far along a line from the subject toward a wanted eye position is free of
 * blocks. The level's own ray cast in the game; replaced by plain geometry in RigChecks.
 */
@FunctionalInterface
public interface Probe {
	/** The free distance from {@code from} toward {@code to} (the whole distance if nothing is in the way). */
	double free(Vec3 from, Vec3 to);

	Probe LEVEL = (from, to) -> {
		var level = Minecraft.getInstance().level;
		if (level == null) return from.distanceTo(to);
		var hit = level.clip(new ClipContext(from, to, ClipContext.Block.OUTLINE, ClipContext.Fluid.NONE, CollisionContext.empty()));
		return hit.getType() == HitResult.Type.MISS ? from.distanceTo(to) : from.distanceTo(hit.getLocation());
	};

	Probe OPEN = (from, to) -> from.distanceTo(to);
}
