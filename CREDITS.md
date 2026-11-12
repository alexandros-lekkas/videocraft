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

## Voice models

The voice tool (`cli/videocraft/voice/`, [docs/VOICE.md](docs/VOICE.md)) downloads these into your Hugging Face cache
on `voice setup`; no weights are in this repository. Licences as stated on each model's page on 2026-11-11.

- [Qwen3-TTS 12Hz 1.7B CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) by the Qwen team
  (Apache-2.0 code and weights), in the 8-bit MLX conversion by
  [mlx-community](https://huggingface.co/mlx-community/Qwen3-TTS-12Hz-1.7B-CustomVoice-8bit), run with
  [mlx-audio](https://github.com/Blaizzy/mlx-audio) (MIT) on [MLX](https://github.com/ml-explore/mlx) (MIT).
- [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) by hexgrad (Apache-2.0 code and weights), with
  [misaki](https://github.com/hexgrad/misaki) (Apache-2.0), spaCy's `en_core_web_sm` (MIT), and for words misaki
  does not know `phonemizer-fork` and espeak-ng (both GPL-3.0; installed into your venv or by you, not distributed
  here).
- [wav2vec2-base-960h](https://huggingface.co/facebook/wav2vec2-base-960h) by Meta AI (Apache-2.0) through
  Hugging Face [transformers](https://github.com/huggingface/transformers) (Apache-2.0) and
  [PyTorch](https://pytorch.org/) (BSD-style), for word timings.

The voices are model presets steered by text descriptions; none is cloned from a person. Generated voices must not
imitate real people.

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
