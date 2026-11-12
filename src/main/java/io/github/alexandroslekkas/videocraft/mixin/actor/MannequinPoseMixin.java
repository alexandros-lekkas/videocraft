package io.github.alexandroslekkas.videocraft.mixin.actor;

import io.github.alexandroslekkas.videocraft.actor.PuppetState;
import io.github.alexandroslekkas.videocraft.actor.Gesture;
import io.github.alexandroslekkas.videocraft.actor.Puppet;
import net.minecraft.client.model.player.PlayerModel;
import net.minecraft.client.renderer.entity.state.AvatarRenderState;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.Unique;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** A mannequin puppet's gestures (wave, point, shrug, ...) on top of vanilla's walk: the arms and an extra head tilt. */
@Mixin(PlayerModel.class)
abstract class MannequinPoseMixin {
	@Unique private static final float[] videocraft$vanilla = new float[Gesture.CHANNELS];

	@Inject(method = "setupAnim(Lnet/minecraft/client/renderer/entity/state/AvatarRenderState;)V", at = @At("TAIL"))
	private void videocraft$gesture(AvatarRenderState state, CallbackInfo info) {
		Puppet p = ((PuppetState) state).videocraft$puppet();
		if (p == null) return;
		PlayerModel model = (PlayerModel) (Object) this;
		float[] v = videocraft$vanilla;
		v[Gesture.RAX] = model.rightArm.xRot; v[Gesture.RAY] = model.rightArm.yRot; v[Gesture.RAZ] = model.rightArm.zRot;
		v[Gesture.LAX] = model.leftArm.xRot; v[Gesture.LAY] = model.leftArm.yRot; v[Gesture.LAZ] = model.leftArm.zRot;
		v[Gesture.HEAD_X] = 0; v[Gesture.HEAD_Z] = 0;
		float[] pose = p.arms(v);
		if (pose == null) return;
		model.rightArm.xRot = pose[Gesture.RAX]; model.rightArm.yRot = pose[Gesture.RAY]; model.rightArm.zRot = pose[Gesture.RAZ];
		model.leftArm.xRot = pose[Gesture.LAX]; model.leftArm.yRot = pose[Gesture.LAY]; model.leftArm.zRot = pose[Gesture.LAZ];
		model.head.xRot += pose[Gesture.HEAD_X];
		model.head.zRot += pose[Gesture.HEAD_Z];
	}
}
