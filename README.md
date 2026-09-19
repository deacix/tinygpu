# TinyGPU (x1476 fork)

A fork of tinygrad's TinyGPU — the macOS DriverKit extension plus the
user-space server that let tinygrad drive an AMD or NVIDIA GPU over
USB4/Thunderbolt. Upstream source: `extra/usbgpu/tbgpu` in
[tinygrad/tinygrad](https://github.com/tinygrad/tinygrad) at commit
`2f0aa884` ("tinygpu: minimal is macos13 for resets", 2026-05-07). The 16
upstream commits touching that directory are preserved as this repository's
history; everything after them is x1476's.

## Why a fork

tinygrad supports NVIDIA over its own ASM2464 dock only. In an Intel
Thunderbolt 5 enclosure (the AORUS RTX5090 AI BOX, bridge `8086:5786`) a
GeForce RTX 5090 (GB202, `10de:2b85`) boots once per power-on and then:

- a clean GSP unload leaves the card in a state where the next GSP boot drops
  the device off the bus at the first BAR1 page-table write;
- the retry issues a PCIe Function-Level Reset through this dext, and the RTX
  5090 never returns from FLR (config reads `0xffff0001`, CRS) — a documented
  firmware defect (Linux `quirk_no_flr` for `10de:2b85`) that only a power
  cycle clears.

This fork changes the reset path and the server so a session can end and the
next one can begin without a power cycle:

- the dext offers `ResetWait(type, options)`: the caller picks the PCIe reset
  type; Blackwell defaults to a hot reset (secondary bus reset from the
  upstream bridge, the reset Linux falls back to), config state is saved and
  restored around it, and the device is polled for readiness (CRS-aware)
  instead of assumed ready after 100 ms;
- the server answers `RESET` only when the device is usable again, and
  survives the device being re-enumerated (reopen, remap, same BAR indices);
- the dext exits when its device goes away (upstream leaked one process per
  re-enumeration);
- `PING` returns a version so a client can tell this build from upstream's
  (server 1.1 = `0x00010100`);
- **several cards** (1.1, 2026-09-18): `server <sock> --device <i>` drives the
  i-th `tinygpu` service in ascending IORegistry-entry-id order — upstream
  always opened the first match, so a second enclosure was unreachable — and
  `PROBE` (cmd 0, previously unanswered) lists them, one line per service,
  `<vendor>:<device>:<registry entry id>:<PCIe link status>:<index>`, before
  any device is opened (as does `PING`). One server per card, each on its own
  socket, is the intended shape; the server itself still takes one client at
  a time. A Mac mini with two RTX 5090s was the case (x1476's multi-eGPU
  plan) — both cards have run PRP side by side on it since 2026-09-18. One
  trap for a client: tinygrad names the remote bus `usb4`, and a second card
  driven this way gets a name like `usb4:1` (x1476 passes `"usb4:%d" % index`
  to `RemotePCIDevice`). Any client logic that recognizes the eGPU by
  `pcibus == "usb4"` then misses every card past the first — x1476's did, and
  its second card ran a day on the host-memory launch path at half speed
  until the check accepted `usb4:<n>` too.

The wire protocol is otherwise unchanged; tinygrad 0.14.0 talks to it as is
(its `APLRemotePCIDevice` connects to `APL_REMOTE_SOCK` — x1476's shim points
each card's worker at its own server).

## Building

```sh
cd installer
./install_nosip.sh --build   # unsigned Debug build, ad-hoc signed
```

Running an ad-hoc-signed driver extension needs System Integrity Protection
off and `systemextensionsctl developer on`; see upstream's
[`docs/tinygpu.md`](https://github.com/tinygrad/tinygrad/blob/master/docs/tinygpu.md)
and `installer/install_nosip.sh`. Signed distribution needs Apple's DriverKit
PCI transport entitlement.

## Signed distribution (evaluated 2026-09-15)

The ad-hoc build above needs SIP off. Two ways to a build that loads on a
stock Mac:

1. **Upstream.** [tinygrad#18199](https://github.com/tinygrad/tinygrad/pull/18199)
   carried the dext and server changes. It was closed on 2026-09-15 under
   tinygrad's policy on AI-assisted contributions (the diff was written with
   Cursor from our measurements), not on technical grounds, so the changes
   live here. If tinygrad ships an equivalent reset path in a signed
   `TinyGPU.zip`, x1476 drops back to the default pin.
2. **Our own Developer ID.** Apple Developer Program membership (USD 99/yr),
   then the restricted DriverKit entitlements
   (`com.apple.developer.driverkit`, `com.apple.developer.driverkit.transport.pci`
   with the PCI vendor ids) requested through Apple's DriverKit entitlement
   form and granted per team; then Developer ID signing, notarization
   (`notarytool`) and the user's one-time driver approval. tinygrad's own
   timeline was about five months from "waiting for entitlement"
   (2025-10-16) to a signed release (2026-03-31), so this is the slow path.
   The bundle ids would change to x1476's, which means a new approval and a
   parser update in x1476 (`egpu.ts`).

Until one of those lands, the fork is an explicit opt-in for SIP-off machines.

## Field notes: NVIDIA cards behind Intel Thunderbolt 5 docks

What two machines taught us on 2026-09-15/16 about running an NVIDIA card
through TinyGPU in an enclosure tinygrad does not support. Everything below
was measured on real hardware with tinygrad 0.14.0 and tiny corp's signed
TinyGPU release (`org.tinygrad.tinygpu.driver2` 1.0.0/3), macOS 27.0, one
kernel log stream (`log stream` on `apciec`, `DART`, `tinygpu`) open the whole
time. Where something is not measured it says so. Related upstream threads:
[#15638](https://github.com/tinygrad/tinygrad/issues/15638),
[#15813](https://github.com/tinygrad/tinygrad/issues/15813),
[#15843](https://github.com/tinygrad/tinygrad/issues/15843),
[#16454](https://github.com/tinygrad/tinygrad/issues/16454),
[#17884](https://github.com/tinygrad/tinygrad/issues/17884), draft
[#15605](https://github.com/tinygrad/tinygrad/issues/15605).

| Mac                 | Card                                      | Enclosure                                          | Link as trained    | Status                                           |
| ------------------- | ----------------------------------------- | -------------------------------------------------- | ------------------ | ------------------------------------------------ |
| Mac Studio M3 Ultra | GeForce RTX 4080 SUPER, AD103 `10de:2702` | Intel "TBT5 Dock", USB4 v2 80 Gb/s                 | Gen1 x4 (2.5 GT/s) | running a PRP test since 2026-09-16, link pinned |
| Mac mini M4 Pro     | 2 × GeForce RTX 5090, GB202 `10de:2b85`   | 2 × AORUS RTX5090 AI BOX, Intel TB5 bridge `8086:5786` | **Gen4 x4 (16 GT/s)** unpinned; Gen1 x4 under the pin | both cards running PRP (server 1.1, `--device`); unpinned since 2026-09-19, no link events |
| Mac mini M4 Pro     | GeForce RTX 4090, AD102 `10de:2684`       | Intel "TBT5 Dock", USB4 v2 80 Gb/s                 | Gen1 x4            | `tinygrad.llm` serving measured (below)          |

### AD103 (Ada): the `Must be table pt=0x0 … 0xffffffffffffffff` failure is the link

The signature from #15638 / #15813 — `NV_GSP.init_golden_image →
mm.page_tables → level_down` asserting on a VRAM read that returns all-ones —
is not BAR1 and not the card. One boot per probe, with the kernel log open:

- Before the GSP boots, VRAM is readable and writable through BAR1 in 4 KB
  bursts.
- After `GSP_INIT_DONE`, every register read, config read and VRAM read
  works and the four RPCs of `init_golden_image` pass. The card survives
  seconds of idle probing.
- The first burst of host **writes** into VRAM takes the link down: 512 B
  survive, 1 KB does not — through BAR1 and through PRAMIN alike — and 512 B
  writes a second apart die at 1.5 KB cumulative. About 100 ms later the root
  port logs `AER uncorrectable status 0xffffffff … Link timeout … Disabling
the port after a link timeout`, and macOS tears the device down and probes
  it again as a new nub.

GSP-RM manages the PCIe link speed itself. The card idles at Gen1 through the
tunnel; the first real traffic makes RM ask the Barlow Ridge bridge for a
faster generation, the retrain never completes, and Apple's root port gives
up. It is the shape of
[NVIDIA/open-gpu-kernel-modules#979](https://github.com/NVIDIA/open-gpu-kernel-modules/issues/979)
on Linux (idle fine, first traffic hard-locks, JHL9480 stuck at Gen1).

**The fix is two entries in the registry table tinygrad hands GSP-RM**
(`NV_GSP.rpc_set_registry_table`, beside its own `RMForcePcieConfigSave` and
`RMSecBusResetEnable`):

| Key                | Value        | Meaning                                                           |
| ------------------ | ------------ | ----------------------------------------------------------------- |
| `RMPcieLinkSpeed`  | `0x800002AA` | gens 2–6 disabled (two-bit fields, `2` = disable), locked at load |
| `PCIEPowerControl` | `0x3`        | enabled + override RM: ASPM off                                   |

With them, 64 KB bursts land, `Device["NV"]` opens, and a NAK-compiled
kernel runs on the card — 4.5 s per self-test (`sm_89`, 16 GB), five times
running, unload → re-open × 3 clean. The installed app has since been running
a GIMPS PRP test on the card (exponent 148,949,431) at 2,215 µs per
iteration, no link events. Measured only on this Intel dock: whether holding
the link at Gen1 costs anything on tinygrad's ASM2464 dock (where the card
may train higher) is **not measured**, so treat the entries as an opt-in for
Intel-bridge enclosures, not a default.

**Update 2026-09-19 — Blackwell does not need the pin, and the pin is
sticky.** On the Mac mini's two RTX 5090s (AORUS boxes, same Intel bridge):

- A 5090 that enumerated at **Gen4 x4** at cold plug ran ~8 h of
  Gerbicz-checked PRP at Gen4 x4 with **no** `RMPcieLinkSpeed` entry and no
  link event in the kernel log — the link never moved. Ada still needs the
  pin (the 4080 SUPER above). x1476 now sends the two entries for every
  family except `GB…`.
- Once sent, `0x800002AA` drops the card to Gen1 x4 and that **survives a hot
  reset plus a fresh GSP boot without the key** (PCIe link-speed state is
  sticky). Only a fundamental reset — a host restart, which keeps the
  Thunderbolt link down long enough, or a power cycle of the enclosure —
  re-enumerates at Gen4. After one restart both cards read `PCIe Gen4 x4`
  under load.
- For compute-bound work the link gen changed nothing: ~245 µs per 4M-point
  squaring at Gen1 and at Gen4 alike, once the launch data (QMD + constant
  bank 0) lived in VRAM inside the BAR1 window instead of Mac RAM. The link
  is bandwidth for residue reads, proof writes and firmware boots, not for
  the kernels.

The full table and the reading procedure: [docs/two-cards-link-and-launch-path-2026-09.md](docs/two-cards-link-and-launch-path-2026-09.md).

What did not fix it: routing the page tables and allocation zeroing through
PRAMIN instead of BAR1 (the substance of draft #15605, which we also carry as
an opt-in) — it worked once the link was pinned, but slower (9.3 s against
4.5 s), and it was not the cause: the failing read in `init_golden_image` was
the link dropping, not BAR1. Capping bulk BAR writes at 256 B did not help
either; a closed write path is not a pacing problem.

Exit policy on Ada: **unload the firmware at exit** (tinygrad's default). A
GSP left resident after the client exited kept DMA-ing into host memory the
helper had unmapped, and macOS 27 on the M3 Ultra answered with a kernel
panic (`[SPTM] VIOLATION_T8110_DART_INVALID_ERR_MASK`, `err_mask
0x80180000` — the "kernel panic on AppleT8110DART" class #15605 reports).
Two such panics on 2026-09-15. The opposite rule holds on Blackwell, below.

### GB202 (Blackwell): sessions, resets, and the poisoned state

- **A clean GSP unload poisons the next boot.** After tinygrad's `atexit`
  (`rpc_unloading_guest_driver`) the card looks fresh — WPR2 `0`, `BOOT_0
0x1b2000a1`, no DART faults — and the next GSP boot dies at its first
  page-table write; the root port logs `logLinkState Link timeout
linksts=0x89000001` → `Disabling the port after a link timeout`, the device
  is torn down and re-probed 400 ms later as a new driver instance. The state
  survives FLR, re-enumeration and four sleep/wake cycles. A power cycle of
  the enclosure clears it; so did a reboot of the Mac (once — the Thunderbolt
  link stays down far longer across a reboot than across a sleep). Same class
  as #16454 and #15638.
- **Keep the GSP resident at exit** instead (make `NV_GSP.fini_hw` a no-op on
  `GB2xx`). The next open finds WPR2 up and tinygrad resets the card itself;
  on a card whose firmware is resident and whose link is healthy the FLR
  returned every time (6 of 6, ~110 ms). Five sessions in a row, no power
  cycle, cold card to kernel result each time: `sm_120`, 31.8 GB, 3.6 s per
  open. A resident GSP is not idle: it reads its old RPC queue in host memory
  about once a second (`DART SID exception … InvalidPTE … read from address
0x80041000`); macOS ignores the faults.
- **After a reset, restore config space yourself.** The reset clears the
  card's config space — Command `0x0`, every BAR `0` — and macOS does **not**
  write the BARs back (its shadow copy is stale once the card was ever
  unresponsive). tinygrad then reads BAR0 as all-ones and the open fails. Read
  the BAR set and the command register before the reset, wait for the card to
  answer with its vendor id (CRS-aware: `0xffff0001` means "not yet"), write
  the set back and set Command `0x7`, and the GSP boot goes through. Keep the
  last good set in a file: a Mac sleep/wake cycle resets the card the same way
  (PERST# through the Thunderbolt port) and leaves the same cleared config
  space, so restoring it before tinygrad reads WPR2 turns sleep/wake into a
  recovery the user can do without touching the enclosure.
- **An FLR on a poisoned card with resident firmware hangs it** in
  Configuration Request Retry Status (`0xffff0001` for as long as we watched,
  over an hour). Linux carries `quirk_no_flr` for `10de:2b85/2b87/2b8c`. An
  FLR on a fresh or healthy resident card never hung (7 of 7). A Mac
  sleep/wake recovers the CRS-hung card: the Thunderbolt port drops and
  re-establishes the tunnel across the sleep, the card answers again with
  cleared config space, and the restore above makes it usable — no enclosure
  power cycle. (Keep the Mac awake with `caffeinate` while working on it;
  every sleep cycle resets the card again.)
- **Every re-enumeration leaves one dext process behind** with upstream's
  dext (`TinyGPUDriver::Stop_Impl` returns without `SUPERDISPATCH`): 25 → 51
  `org.tinygrad.tinygpu.driver2` processes over one day on the mini, 22 in
  twenty minutes on the Studio while a worker re-opened a failing card every
  60 s. Hence: **never re-open a failed card on a timer.** Stand it down
  until a person asks for another attempt.
- **A client whose device vanishes mid-call wedges the helper.** tinygrad's
  `TinyGPU server` blocks in `IOConnectCallMethod` against the torn-down
  driver instance (uninterruptible; `kill -9` has no effect), every later
  client spawns another server that blocks the same way, and once enough of
  them pile up `ioreg` and `system_profiler` hang too. Only a reboot clears
  it — which also happens to be the reboot that clears the poisoned card.
- **"Left the bus" is decided after waiting.** A failed firmware boot knocks
  the card off the link for a moment: the handle the open failed on reads
  all-ones, half a second later its helper dies (`BrokenPipeError`), and
  macOS has the card back, `Link up` with programmed BARs, within the minute.
  Reading "lost" off the old handle is a coin flip; release it, re-probe with
  fresh connections for up to 30 s, and let `system_profiler SPPCIDataType`
  (the vendor's card behind a `Thunderbolt@` slot) decide only when the card
  never answers again.

### Applying this

The registry entries and the exit/reset rules are facts about GSP-RM, the
card and macOS, not about a tinygrad version. Where they are applied is:

- **tinygrad 0.14.0** (the wheel on PyPI; the macOS device is
  `APLRemotePCIDevice`, `pci_dev.pcibus == "usb4"`): the x1476 desktop app
  patches tinygrad in-process before `Device["NV"]` —
  `NV_GSP.rpc_set_registry_table` (the table above, remote device only),
  `NV_GSP.fini_hw` (resident on `GB2xx`, unload otherwise),
  `APLRemotePCIDevice.reset` (save → reset → wait → restore) plus a restore
  at probe time, and `APLRemotePCIDevice.ensure_app` (a no-op: the app
  installs TinyGPU.app itself, so tinygrad never downloads or re-installs it
  behind the user's back). The same 0.14.0 protocol has **no host unmap**:
  a session gets 128 host mappings for its lifetime, tinygrad's allocator
  takes 32 of them for 2 MB staging buffers, and each live mapping holds a
  file descriptor in the client (macOS starts a process at 256), so a
  long-running client trims the staging count and raises `RLIMIT_NOFILE`.
- **tinygrad master** has since replaced `APLRemotePCIDevice` with
  `RemotePCIDevice` over `REMOTE=host:port` and added `UNMAP_SYSMEM`; the
  patch points above do not exist there, `rpc_set_registry_table` still
  carries the same two-entry literal. The upstream form we would propose is
  an opt-in flag, so the default path and tinygrad's own dock are untouched:

  ```python
  # tinygrad/runtime/support/nv/ip.py, rpc_set_registry_table
  table = {'RMForcePcieConfigSave': 0x1, 'RMSecBusResetEnable': 0x1}
  # NVIDIA behind an Intel Thunderbolt 5 dock: hold the link at Gen1 and turn ASPM off,
  # or GSP-RM's first retrain through the tunnel drops the link (tinygrad#15638, #15813)
  if getenv("NV_PCIE_GEN1", 0): table |= {'RMPcieLinkSpeed': 0x800002AA, 'PCIEPowerControl': 0x3}
  ```

  What x1476 ships (2026-09-19) is the family-aware form of the same rule:
  the two entries for every card whose `chip_name` is not `GB…`, nothing for
  Blackwell (RM keeps the link where the enclosure trained it), with an env
  override in both directions — see the update under the AD103 section.

- **This fork's dext** adds the reset half for Blackwell: a `ResetWait` RPC
  (hot reset — secondary bus reset from the upstream bridge, the reset Linux
  falls back to for these ids — for `GB2xx`, FLR otherwise; config state
  saved and restored in the dext; CRS-aware readiness poll up to 30 s), a
  `Ping`, an exit on `Stop`, a synchronous re-enumeration-safe server `RESET`,
  and a server that survives its device going away. **Not yet validated on
  the card**: the fork builds and signs, and the FLR/BAR-restore behaviour it
  formalizes is what the measurements above show, but the "resident GSP →
  in-process hot reset → boot, × 5" run, hot reset with
  `kIOPCIDeviceResetOptionTerminate`, and whether a hot reset clears the
  poisoned state where an FLR and a sleep/wake do not, are still open. Results
  go here when they exist.

### `tinygrad.llm` on the same dock (2026-09-16)

tinygrad's own OpenAI-compatible server, run on the Mac mini with the **RTX
4090** (AD102 `10de:2684`) behind the same **Intel TBT5 Dock** (link trained
Gen1 x4), macOS 27.0, tiny corp's signed TinyGPU, tinygrad 0.14.0 +
tinymesa 25.2.7.2, `DEV=NV:NAK`, no Docker, through a launcher that applies
the session policy above (link pin, Ada unload-at-exit). The model is
`Qwen3-8B-Q4_K_M.gguf` (5.03 GB, the `qwen3:8b` alias).

| Measurement                                 | Result                                                                                         |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Device open                                 | 24.3 s the first time (the GSP firmware fetch, 63.6 MB), 4.2–4.4 s after                       |
| `--benchmark 20`, run 1                     | tokens 1–3 at 6.4 / 3.2 / 2.2 s (JIT capture), then **274.8 ms/token = 3.63 tok/s**, 17.1 GB/s |
| `--benchmark 20`, run 2 (kernel cache warm) | identical: 3.64 tok/s, 17.2 GB/s — compile is not the cost                                     |
| `--serve`, 14-token prompt, 32 out          | `prefill: 34 tok/s`, `gen: 4 tok/s`, 9.0 s                                                     |
| `--serve`, 3,687-token prompt, 64 out       | `prefill: 30 tok/s` (about two minutes), `gen: 3 tok/s`, 144.7 s                               |
| Cycles                                      | about twenty opens over the day, no power cycle, no markers, dext instances 7 at every count   |

17 GB/s effective against the card's ~1 TB/s says where the time goes:
decode is bound by per-kernel launch round-trips through the TinyGPU helper
and the tunnel, not by the card. The community's "5–8 tok/s on a 5090"
reports are consistent with 3.6 on a 4090. What an eGPU buys for LLM
serving on a Mac today is a second device with its own memory and fast
first tokens, not faster generation.

Three things learnt on the way, none of them about the dock:

- **The tinygrad 0.14.0 wheel on PyPI cannot run `python -m tinygrad.llm`.**
  `tinygrad/llm/model.py` imports `tinygrad.llm.kernels.amd`
  unconditionally, and the wheel ships `tinygrad/llm/` without `kernels/`:
  `pyproject.toml`'s explicit `packages` list names `'tinygrad.llm'` but not
  `'tinygrad.llm.kernels'` (`package-data` does not recurse), so the
  subpackage never made it into the wheel — on `master` too, as of this
  writing. The failure is `ModuleNotFoundError: No module named
'tinygrad.llm.kernels'`, right after the device opened. Workaround until
  the list is fixed: drop the tag's file beside the wheel —
  `tinygrad/llm/kernels/__init__.py` (empty) and
  `tinygrad/llm/kernels/amd.py` from
  `https://raw.githubusercontent.com/tinygrad/tinygrad/v0.14.0/tinygrad/llm/kernels/amd.py`
  (36,883 bytes, sha256
  `69982fea1d378bd599a2949c8a012414749cb2fbaf93fc6d0ed26c198a83794a`).
- **`WPR2 is up. Issuing a full reset.` is logged on every open of this
  AD102**, after a clean exit as much as after a killed one: the
  guest-driver unload does not lower WPR2 on Ada, tinygrad resets the card
  at each open, and that path works. The line is therefore not evidence of
  a resident GSP — instrument `NV_GSP.rpc_unloading_guest_driver` if that
  is the question (it runs in ~31 ms at a clean exit).
- **A wrapper that stops `tinygrad.llm` with SIGTERM skips tinygrad's
  `atexit`**, and the GSP finalizer — the exit policy above — is an atexit
  hook: the card's firmware stays resident on every stop. Python's default
  SIGTERM action ends the process without unwinding; a process started as a
  background job also inherits SIGINT ignored, so Python installs no
  `KeyboardInterrupt` handler and `kill -INT` does nothing. Install a
  SIGTERM handler that raises `SystemExit(0)` (and restore
  `signal.default_int_handler`) before the open: measured, the unload RPC
  then runs on the signal path exactly as on a clean exit.

### Other things we hit

- **NVIDIA kernels compile on the Mac without Docker.** tinygrad's docs send
  NVIDIA users to a Docker-hosted CUDA toolchain; `pip install
tinymesa==25.2.7.2` (Mesa's NAK compiler as a 6.7 MB macOS arm64 wheel) with
  `DEV=NV:NAK` and `MESA_PATH=<site-packages>/tinymesa/libtinymesa.dylib`
  compiles tinygrad's generated kernels on the Mac — the self-tests above are
  NAK-compiled kernels.
- **Loading your own nvcc cubins through tinygrad's NV runtime** (`dev.runtime`
  over a `TinyELF`): nvcc-built SASS reads `blockDim`/`gridDim` from constant
  bank 0 (Blackwell at `0x360`/`0x370`, earlier parts at `0x0`/`0xc`) and
  tinygrad never writes them, so every `blockDim` reads as 0 and grid-stride
  loops never advance; fill them per launch. tinygrad keeps the **last**
  register-count record of a cubin's global `.nv.info`, so a multi-kernel
  cubin needs a per-kernel view with that kernel's records last. The first
  QMD of a re-submitted bound queue launches while the previous pass still
  runs; a wait-for-idle at the queue head fences it. And ptxas 12.8
  miscompiled our fused NTT tile for `sm_120` at every level above `-O0`;
  CUDA 13.1 is right at `-O3`.
- **macOS App Management** guards an existing `.app` signed by another Team
  ID — `sudo` and root shells answer `EPERM`; only a grant to the replacing
  app (or Full Disk Access) lets it overwrite `/Applications/TinyGPU.app`,
  and the grant takes effect after that app relaunches. Creating a new bundle
  there is not guarded. An installer that must coexist with tiny corp's own
  `setup_tinygpu_osx.sh` adopts an identical bundle and moves a different one
  aside rather than `ditto`-ing over it.

## License

MIT, as upstream (`LICENSE`, Copyright (c) 2024, the tiny corp).
