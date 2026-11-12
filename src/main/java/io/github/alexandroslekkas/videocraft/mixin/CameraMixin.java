package io.github.alexandroslekkas.videocraft.mixin;

import io.github.alexandroslekkas.videocraft.api.Pose;
import io.github.alexandroslekkas.videocraft.director.Director;
import net.minecraft.client.Camera;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfoReturnable;

/**
 * After the game has put the camera on its entity, the current shot's rig moves it. In third-person shots the player
 * stays the camera entity (vanilla draws the local player only then), so the game still renders and animates it.
 * No take, or a first-person shot: nothing changes.
 */
@Mixin(Camera.class)
abstract class CameraMixin {
	@Shadow protected abstract void setPosition(double x, double y, double z);
	@Shadow protected abstract void setRotation(float yRot, float xRot);

	@Inject(method = "alignWithEntity(F)V", at = @At("TAIL"))
	private void videocraft$rig(float partialTick, CallbackInfo info) {
		Pose pose = Director.camera(partialTick);
		if (pose == null) return;
		setRotation(pose.yaw(), pose.pitch());
		setPosition(pose.x(), pose.y(), pose.z());
	}

	/** The rig's lens for this frame, exactly: no sprint, speed-effect or water FOV on a filmed view. */
	@Inject(method = "calculateFov(F)F", at = @At("RETURN"), cancellable = true)
	private void videocraft$lens(float partialTick, CallbackInfoReturnable<Float> info) {
		double fov = Director.lens();
		if (!Double.isNaN(fov)) info.setReturnValue((float) fov);
	}
}
