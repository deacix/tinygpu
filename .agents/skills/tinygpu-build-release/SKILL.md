---
name: tinygpu-build-release
description: Use when building, signing, notarizing, installing or releasing the TinyGPU x1476 fork — the xcodebuild flows, entitlements, the dist zip + sha256 contract, tags, and the NoSIP dev path.
---

# TinyGPU build and release (x1476 fork)

Five build paths exist. Nothing in this repo builds off macOS: on any other
host only shell syntax is checkable (`bash -n <script>`).

## The five paths

1. **Dev build (SIP-off)** — `cd installer && ./install_nosip.sh`:
   checks `csrutil status` (exits if SIP is on), unsigned Debug
   `xcodebuild`, ad-hoc signs with the **NoSIP** entitlements
   (`TinyGPUDriver.NoSIP.entitlements`, match-anything), copies to
   `/Applications` and runs `TinyGPU install` to activate the dext.
   `--build` stops before install.
2. **Fork release (ad-hoc)** — `cd installer && ./build_fork_release.sh`:
   ad-hoc Release build with the **vendor-scoped** entitlements
   (`TinyGPUDriver.Release.entitlements`), strips the provisioning
   profiles, `codesign --verify --deep --strict`, then writes
   `installer/dist/TinyGPU.zip` and `TinyGPU.zip.sha256` (the shape
   x1476's engines manifest pins: `tinygpu.app.url` + sha256).
3. **Developer ID signed (tinygrad team)** — `installer/build_and_sign.sh`
   / `build_and_sign_nv.sh`: Release build, embeds provisioning profiles
   from `../profiles/` (NOT in this repo), signs with
   `Developer ID Application: tinygrad, Corp. (9YG3G8543N)`, hardened
   runtime + timestamp. `_nv` uses the NV.Release entitlements.
4. **Notarize** — `installer/notary_tool.sh`: zip → `xcrun notarytool
   submit --keychain-profile <named> --wait` → `stapler staple`. Needs the
   named keychain profile on the build Mac.
5. **CI release (tag)** — pushing a `v1.1.0-fork.<n>` tag runs
   `.github/workflows/fork-release.yml` on `macos-26`: path 2's script
   unchanged, then `gh release create` publishes `TinyGPU.zip` and
   `TinyGPU.zip.sha256` as that tag's GitHub release (the annotated tag's
   subject/body become the release title/notes). A pull request touching
   `installer/**` runs the same build as the `fork-release` check without
   publishing. CI does not Developer ID sign, notarize, or run hardware
   tests. The local script stays the dev path.

## Rules

- Entitlements are load-bearing. Release builds carry vendor-scoped ones
  (NVIDIA `0x10de`, AMD `0x1002`); NoSIP dev builds use the match-anything
  set. Never mix the two. AMFI accepts the restricted entitlements on an
  ad-hoc signature only with SIP off.
- Regenerate `installer/dist/TinyGPU.zip.sha256` with
  `build_fork_release.sh`; never hand-edit it. The zip itself is
  gitignored (`*.zip`); the `.sha256` is checked in. The pinning rule and
  the recorded facts:
  - Consumers pin the SHA-256 of the downloaded `TinyGPU.zip` itself, and
    cross-check it against the release's `.sha256` asset.
  - The checked-in file records a local build.
  - fork.4's `.sha256` asset does not match its zip: the asset says
    `d04a8955…`, the zip hashes to `65df3806…`, which equals the
    checked-in file.
  - CI-built releases (fork.5 on) write the zip and its `.sha256` from
    one build.
- Release tags are `v1.1.0-fork.<n>` (see `git tag`). The wire protocol is
  frozen; a release never changes it without a server version bump
  (`PING` returns the version).
- A `.dext` bundle is flat: its `Info.plist` sits at the bundle root, not
  under `Contents/`.
- `ditto -c -k --keepParent` is the only zip shape x1476 extracts
  (`ditto -xk`); never re-zip with another tool.

## Gotchas

- Ad-hoc builds need SIP off plus `systemextensionsctl developer on` — an
  explicit opt-in. On a SIP-on Mac use tinygrad's signed release instead.
- The ad-hoc path removes `embedded.provisionprofile` from both bundles:
  an ad-hoc build must not carry tinygrad's team profiles.
- `install_tinygpu.sh` (repo root) only activates an already-installed
  `/Applications/TinyGPU.app`; it exits 1 when the app is absent.