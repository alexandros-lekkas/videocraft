package io.github.alexandroslekkas.videocraft.actor;

/** What a render state knows about the puppet it was extracted from (added to EntityRenderState by a mixin). */
public interface PuppetState {
	Puppet videocraft$puppet();

	void videocraft$puppet(Puppet puppet);
}
