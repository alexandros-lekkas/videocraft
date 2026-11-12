package io.github.alexandroslekkas.videocraft.mixin.actor;

import net.minecraft.client.entity.ClientMannequin;
import net.minecraft.world.entity.player.PlayerSkin;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;
import org.spongepowered.asm.mixin.gen.Invoker;

import java.util.Optional;
import java.util.concurrent.CompletableFuture;

/** A mannequin takes its skin when its lookup finishes, in its tick; a puppet's skin is settled on render too. */
@Mixin(ClientMannequin.class)
public interface ClientMannequinAccess {
	@Accessor("skinLookup") CompletableFuture<Optional<PlayerSkin>> videocraft$skinLookup();

	@Accessor("skinLookup") void videocraft$setSkinLookup(CompletableFuture<Optional<PlayerSkin>> value);

	@Invoker("setSkin") void videocraft$setSkin(PlayerSkin skin);
}
