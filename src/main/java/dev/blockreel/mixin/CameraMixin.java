package dev.blockreel.mixin;

import dev.blockreel.api.Pose;
import dev.blockreel.director.Director;
import net.minecraft.client.Camera;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Shadow;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

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
	private void blockreel$rig(float partialTick, CallbackInfo info) {
		Pose pose = Director.camera(partialTick);
		if (pose == null) return;
		setRotation(pose.yaw(), pose.pitch());
		setPosition(pose.x(), pose.y(), pose.z());
	}
}
