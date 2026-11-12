# Credits

## Where videocraft comes from

videocraft grew out of the launch-trailer recorder of [T3 Craft](https://github.com/alexandros-lekkas/t3craft)
(MIT, same author): its scripted demo recorder, the human input model for the mouse and keyboard, the overlay text
and the mannequin actors were the prototype that this project generalises into a script format, a run store and a
plugin API.

## Built on

- [Fabric](https://fabricmc.net/): Fabric Loader, Fabric API and the Loom Gradle plugin (Apache-2.0), and the Mixin
  library (MIT) they ship with.
- [FFmpeg](https://ffmpeg.org/) (LGPL/GPL, with libx264): every encode, cut and export. videocraft calls the
  `ffmpeg` and `ffprobe` you installed; it does not bundle them.
- [Gradle](https://gradle.org/) (Apache-2.0), through the checked-in wrapper.
- Python's standard library; the [Eclipse Temurin](https://adoptium.net/) JDK in CI.
- The modpack in `modpack/pack.toml` references other mods by download (Lithium, FerriteCore, ImmediatelyFast) under
  their own licences; none of their code is in this repository.

## Minecraft

**Minecraft is a trademark of Mojang Synergies AB / Microsoft. videocraft is an unofficial tool. It is not approved by
or associated with Mojang or Microsoft.** It follows the [Minecraft Usage Guidelines](https://www.minecraft.net/en-us/usage-guidelines).

**No game assets are in this repository.** No textures, models, sounds, music or fonts from Minecraft are committed,
and none are distributed with the mod. The game itself is downloaded for development by Loom from Mojang's servers.
Music and sounds for an edit are read at export time from the user's own local game assets
(`~/.gradle/caches/fabric-loom/assets`). The images in `assets/` are original, drawn by code in a block style.

## The benchmark

The benchmark in `docs/benchmarks/` studies the *form* of third-party videos (shot lengths, cutting rhythm, how text
and sound are used) to set a quality bar. It reuses none of their content: no footage, frames, audio, characters,
script or text from them is in the repository or in anything videocraft produces. Their characters and sets are
replaced by our own.

## Contributors

Everyone who has opened an issue or a pull request; see the
[contributors graph](https://github.com/alexandros-lekkas/videocraft/graphs/contributors).
