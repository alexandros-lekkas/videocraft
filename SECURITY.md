# Security

videocraft is a development tool: a Fabric mod that does nothing unless the CLI starts a take, and a command line
that runs on your own machine. It has no server, no accounts and no telemetry. Its attack surface is small, and we
want to keep it that way.

## What runs, and where

- **The control port.** While a take runs, the mod listens on **127.0.0.1 only**, on one of the ports 25750–25752
  (one per client slot). It speaks JSON over HTTP: `GET /status` (how far the take is) and `POST /quit` (stop the
  client cleanly). Requests whose `Host` header is not `127.0.0.1:<port>` or `localhost:<port>` are refused (a
  defence against DNS rebinding), and so is any request carrying an `Origin` header (a web page in a browser). The
  server stops with the client.
- **The game.** The client runs hidden and muted, in the checkout's own `run-game/` folder; the CLI refuses to point
  it at a real Minecraft folder. It opens a single-player world and needs no network for a take, beyond Loom's
  downloads of the game when you build.
- **The CLI.** Python standard library only. It runs `ffmpeg`, `ffprobe` and the Gradle wrapper, and reads music and
  sounds from the local game asset cache at export time.

## What to report

Please report privately anything that lets something other than you on your machine, or a remote party, act through
videocraft. For example:

- reaching the control port from another host, from a browser page, or through a request the checks above let
  through;
- a way for a shot script, a plan, a set file or a plugin's parameters to run a command on the host, or read or
  write files outside the checkout (`run-game/`, `runs/`, `cache/`) and the paths you passed;
- anything that makes the game or the CLI read or write a real Minecraft folder;
- a way for the CLI to pass untrusted text to a shell.

Not security issues (open a normal issue): a take that crashes or hangs, a slot that is not released, `/quit`
stopping your own take from another program you run.

Scripts run Minecraft commands inside the take's own world by design (`do = "command"`); treat a shot script from
someone else like any other code you run.

## How to report

Use GitHub's private vulnerability reporting:
**[Report a vulnerability](https://github.com/alexandros-lekkas/videocraft/security/advisories/new)** (Security tab →
Advisories → Report a vulnerability). Include the commit (`git rev-parse --short HEAD`), your platform, and the
smallest steps or script that shows the problem. Please do not open a public issue or pull request for it first.

You will get a reply within a week. Fixes land on `main`; there are no maintained release branches yet, so the fix
is "update to the latest commit". We credit reporters in the advisory unless you ask us not to.
