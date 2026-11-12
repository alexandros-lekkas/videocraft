# Starter issues

Well-scoped first contributions, written up before they are filed on GitHub (where they carry the
`good first issue` label). Each one says why it matters, what "done" means, and where to start reading.
Read [CONTRIBUTING.md](../../CONTRIBUTING.md) first.

| File | Title | Area | Needs the game running |
|:--|:--|:--|:--|
| [01-linux-xvfb.md](01-linux-xvfb.md) | Run takes on Linux under `xvfb-run` | CLI, mod | yes (Linux) |
| [02-windows-paths.md](02-windows-paths.md) | Make the CLI work on Windows | CLI | partly |
| [03-sodium-capture-parity.md](03-sodium-capture-parity.md) | Check capture parity with Sodium | mod | yes |
| [04-handheld-rig.md](04-handheld-rig.md) | Add a `handheld` camera rig | mod | yes |
| [05-set-library-entry.md](05-set-library-entry.md) | Add a set to the set library | sets | yes |
| [06-export-preset-square.md](06-export-preset-square.md) | Add a square 1080×1080 export preset | edit | no (re-cut) |
| [07-plugin-guide.md](07-plugin-guide.md) | Write the plugin guide and an example plugin | docs | yes |
| [08-doctor-json.md](08-doctor-json.md) | `videocraft doctor --json` | CLI | no |

Each file starts with a `# Title` line and a `Labels:` line, so they can be filed with
`gh issue create --title "<title>" --body-file <file> --label <labels>` (strip the first two lines from the body).
