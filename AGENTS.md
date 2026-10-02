# AGENTS.md

## What this is

TinyGPU (x1476 fork): the macOS DriverKit extension plus the user-space
server that let tinygrad drive an AMD or NVIDIA GPU over USB4/Thunderbolt.
Forked from tinygrad `extra/usbgpu/tbgpu` at `2f0aa884`; the 16 upstream
commits are preserved as history and everything after them is this fork's
(the reset path, `ResetWait`, multi-card `server --device <i>` / `PROBE`,
server 1.1; `IMPORT_SYSMEM_FD`, server 1.2). Languages: C++ (dext), C
(server), Swift (installer app/CLI), Bash (build and release). The wire
protocol only grew commands; tinygrad 0.14.0 talks to it as is.

## Build, test, run

All build/sign/install commands need macOS with Xcode; on any other host
only shell syntax is checkable (`bash -n <script>`). Every line below is
labelled with what was actually run where.

- Build (dev, SIP-off): `cd installer && ./install_nosip.sh --build` —
  **macOS-only**; checks `csrutil status` (refuses SIP on), `xcodebuild`
  Debug build, ad-hoc signs with the NoSIP entitlements.
- Build (fork release): `cd installer && ./build_fork_release.sh` —
  **macOS-only**; ad-hoc Release build with vendor-scoped entitlements,
  writes `installer/dist/TinyGPU.zip` and `TinyGPU.zip.sha256` (the shape
  x1476's engines manifest pins).
- Sign (tinygrad team): `installer/build_and_sign.sh` /
  `installer/build_and_sign_nv.sh` — **macOS-only**; Developer ID signing;
  needs provisioning profiles in `../profiles/` (not in this repo).
- Notarize: `installer/notary_tool.sh` — **macOS-only**; `notarytool
  submit` + `stapler staple`; needs the named keychain profile.
- Install the driver: `./install_tinygpu.sh` — macOS; verified here that it
  exits 1 with `TinyGPU.app not found in /Applications` when the app is
  absent, otherwise runs `TinyGPU install`.
- Stop servers: `./kill_tinygpu.sh` — `pkill -f "tinygpu.sock"`; verified
  here: exits 1 when no server matches (pkill semantics).
- Test: none — there is no test suite. Validation happens on hardware and
  is recorded as field notes (`README.md`, `docs/`). The one scripted check
  is `python3 tests/import_sysmem_smoke.py --cards 0,1` (server 1.2's
  import, on a Mac with two cards and their servers free).

## Repository layout

- `installer/TinyGPUDriverExtension/` — the DriverKit dext (C++/IIG).
- `installer/Shared/` — the userspace C server (`server.c`, unix-socket
  protocol: `PROBE`/`PING`/`MAP_BAR`/`CFG_*`/`RESET`/`MMIO_*`/`SYSMEM_*`)
  and the Swift app + CLI runner.
- `installer/macOS/` — app target resources and entitlements.
- `installer/*.sh` — build, sign, notarize and dev-install scripts.
- `installer/dist/` — release output; the `.sha256` is checked in, the zip
  is gitignored (`*.zip`).
- `docs/` — measured field notes (convention: `tinygpu-field-notes` skill).

## Conventions

- Never rewrite the preserved upstream history; the fork's work sits on top.
- Regenerate `installer/dist/TinyGPU.zip.sha256` with
  `build_fork_release.sh`; never hand-edit it.
- Entitlements are load-bearing: Release builds carry vendor-scoped ones
  (NVIDIA `0x10de`, AMD `0x1002`); NoSIP dev builds use the match-anything
  set. Do not mix the two.
- Field notes state hardware, dock, link state and what is validated vs
  not — never overclaim.
- Commit style: `type(scope): subject` (see `git log`).

## Agent config that already applies

- `.agents/skills/` — agent skills: Legwork platform process skills
  (planning, review, security, git) plus this repo's domain skills
  (`tinygpu-build-release`, `tinygpu-field-notes`, `root-cause-debugging`)
  and vetted installs.
- `.legwork/hooks.yml` — Legwork run hooks (security/quality gates on
  commit, review on done).
- Skill installs are project-scope under `.agents/skills/`
  (`npx skills add <source> --skill <name> --agent universal --copy`),
  never `-g` — a HOME-scope install has no repository provenance or
  security baseline. Pins live in `skills-lock.json` (source + `ref` +
  hash); `fetch-and-scan` runs before every install. First-party skills
  get a `sourceType: "local"` row (content hash only — a local skill has
  no upstream ref to pin).
- Attribution: `c-bounds-safety` and `audit-xcode-security-settings` are
  Apple-authored guidance exported from Xcode 27, redistributed by
  `superagents-lab/xcode27-skills` @ `6f9ff8d5`; upstream grants no
  license over Apple's content. Instructions-only use.
- Debugging discipline (2026-09-30): covered by the first-party
  `root-cause-debugging` skill — nothing is missing from the tree. The
  upstream `systematic-debugging` (`obra/superpowers`) is deliberately
  not installed: its bytes failed `fetch-and-scan` (LSC-HU-005, an emoji
  presentation selector in `find-polluter.sh:43`) and third-party skill
  content may not be edited; an operator-waiver proposal is recorded on
  issue #13. Revisit only if that waiver is granted or upstream fixes
  the byte.

## Gotchas

- Loading the ad-hoc-signed dext needs SIP off plus
  `systemextensionsctl developer on` — an explicit opt-in; AMFI rejects the
  restricted entitlements on an ad-hoc signature while SIP is on.
- Nothing here builds on Linux; `xcodebuild` lives in 4 scripts
  (`install_nosip.sh`, `build_fork_release.sh`, `build_and_sign.sh`,
  `build_and_sign_nv.sh`).
- The server answers `RESET` only when the device is usable again; clients
  must not assume readiness after reset.
- Client trap: tinygrad names the remote bus `usb4`, and a second card gets
  `usb4:1` — match `usb4:<n>`, not `usb4` (see README field notes).