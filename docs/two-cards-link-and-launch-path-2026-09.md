# Two RTX 5090s behind AORUS RTX5090 AI BOXes on a Mac mini — the link, the launch path, and the pin

Field measurements, 2026-09-18/19. Self-contained: everything referenced here
is public. The short form is in the README's field notes; this page carries
the numbers.

## Setup

| Item        | Value                                                                                                             |
| ----------- | ----------------------------------------------------------------------------------------------------------------- |
| Host        | Mac mini M4 Pro, macOS 27.0                                                                                       |
| Enclosures  | 2 × GIGABYTE AORUS RTX5090 AI BOX — Intel Thunderbolt 5 bridge `8086:5786`, one per Thunderbolt port              |
| Cards       | 2 × GeForce RTX 5090, GB202 `10de:2b85` (Blackwell), BAR1 256 MiB                                                 |
| Host links  | 40 Gb/s per enclosure (`system_profiler SPThunderboltDataType`)                                                   |
| Driver path | tinygrad 0.14.0's userspace NVIDIA path over this fork's TinyGPU (server 1.1, `server <sock> --device <i>`)      |
| Workload    | GIMPS PRP squarings, 4M-point NTT (PRPLL built against a device server that runs its kernels through tinygrad)    |
| Reading     | `pcieLink` from the card's PCI Express capability (Link Status: gen = bits 3:0, width = bits 9:4); `system_profiler SPPCIDataType` → `Link Speed`; kernel log for `apciec … Link timeout … Disabling the port` |

## The table

| build                    | card | pcieLink    | launch data | µs / iteration (whole machine busy) |
| ------------------------ | ---- | ----------- | ----------- | ----------------------------------- |
| before the fix           | 0    | Gen1 x4     | VRAM        | ~245–255                            |
| before the fix           | 1    | **Gen4 x4** | **host**    | **~450–485**                        |
| launch-path fix          | 0    | Gen1 x4     | VRAM        | ~250–253                            |
| launch-path fix          | 1    | Gen1 x4     | VRAM        | **~229–260**                        |
| pin skipped on Blackwell | 0    | Gen1 x4     | VRAM        | ~236–258 (sticky Gen1, see 4)       |
| pin skipped on Blackwell | 1    | Gen1 x4     | VRAM        | ~239–250 (sticky Gen1, see 4)       |
| … + one Mac restart      | 0    | **Gen4 x4** | VRAM        | ~233–257                            |
| … + one Mac restart      | 1    | **Gen4 x4** | VRAM        | ~244–256                            |

Zero `Link timeout` / `Disabling the port` events in the kernel log across all
of it, including the two restarts and every re-open.

## 1. The 2× was the launch path, not the link (a client bug)

The Gen4 card was the _slower_ one. Its HELLO said why:
`launchPath: sysmem — "a local card keeps tinygrad's own placement"`.

tinygrad names its macOS remote device's bus `usb4`. A second card driven
through `--device 1` is constructed with the bus `usb4:1` (the client passes
`"usb4:%d" % index` to `RemotePCIDevice` so the lock and the dev_id are its
own). Two gates in the client recognized "this is an eGPU" by
`pcibus == "usb4"` — so the second card was read as a local PCIe card, and
tinygrad's small-BAR placement rule put its launch data (the QMD and constant
bank 0 of every kernel) in **host memory**, fetched across the Thunderbolt
tunnel on every launch: a fixed ~40 µs per kernel, seven kernels a squaring.

The fix is the predicate:

```python
def _bus_is_usb4(pcibus) -> bool:
    return isinstance(pcibus, str) and (pcibus == "usb4" or pcibus.startswith("usb4:"))
```

With it the second card takes the same VRAM window as the first — one
`force_devmem` allocation made first thing after the device opens so its
physical address sits inside the 256 MiB BAR1 aperture, from which every
graph's kernargs are carved — and runs at the first card's rate. The
mis-gate had also kept the second card from the link pin, the PRAMIN route and
the reset guard, all behind the same check.

**If you write a client for this fork's `--device` server: accept
`usb4:<n>`.**

## 2. Link gen does not change compute throughput

~245 µs per squaring at Gen1 x4 and at Gen4 x4 alike, once launch data lives
in VRAM. What still crosses the link is a residue read per check (64 MB, ≈60 ms
at Gen1, ≈16 ms at Gen4), a proof residue per power-of-two step, kernel and
firmware uploads at start — well under 0.1 % of a run. The link is bandwidth
for that traffic, not for the kernels. A Gen3 cap costs a compute-bound
workload nothing.

## 3. Blackwell does not need the link pin; Ada does

The pin: two entries added to the registry table tinygrad hands GSP-RM
(`NV_GSP.rpc_set_registry_table`, beside its own `RMForcePcieConfigSave` and
`RMSecBusResetEnable`):

| Key                | Value        | Meaning                                                              |
| ------------------ | ------------ | -------------------------------------------------------------------- |
| `RMPcieLinkSpeed`  | `0x800002AA` | two-bit fields from Gen2 up, `2` = disabled → gens 2–6 off; bit 31 = locked at load |
| `PCIEPowerControl` | `0x3`        | enabled + override RM: ASPM off                                       |

- **Ada** (RTX 4080 SUPER, AD103, Intel "TBT5 Dock", Mac Studio M3 Ultra):
  needs it. After `GSP_INIT_DONE` every read works; the first ~1 KB of host
  writes into VRAM makes RM ask the bridge for a faster gen, the retrain never
  completes, and Apple's root port disables the port ~100 ms later. With the
  two entries, 64 KB bursts land and the card runs (at Gen1 x4). Same shape as
  NVIDIA/open-gpu-kernel-modules#979 on Linux.
- **Blackwell** (both RTX 5090s here): does not. A card that enumerated Gen4 x4
  at cold plug ran **~8 h of Gerbicz-checked PRP at Gen4 x4 with no table at
  all** (17:50–01:57 local, ~34 M iterations) — the stretch the bug in §1 had
  left it unpinned — with zero link events. The link never moved. Gen4 x4
  _operation_ over this tunnel is fine; it is the Gen4 _retrain_ that #979
  documents dropping the card, and on this path RM never requested one.

So the shipped rule is family-aware: the two entries for every card whose
`chip_name` is not `GB…` (the same predicate that decides GSP stays resident
on Blackwell), nothing for Blackwell, with an env override in both directions.

## 4. The pin is sticky — only a fundamental reset clears it

The moment the fixed client pinned card 1 (§1 had kept it unpinned), it fell
from Gen4 x4 to Gen1 x4. Then, with the pin skipped for Blackwell, **both cards
stayed at Gen1 x4** under load: the "gens 2–6 disabled" state survives a hot
reset (secondary bus reset) and a fresh GSP boot _without_ the key. RM without
a table leaves the link where it finds it — which is exactly why the unpinned
card had kept its cold-plug Gen4.

A **restart of the Mac** was enough (the Thunderbolt links stay down far
longer across a reboot than across a sleep; an enclosure power cycle works
too): both enclosures re-enumerated at 16.0 GT/s, both cards came up
`launch path vram · PCIe Gen4 x4`, resumed from their checkpoints at
233–257 µs/it, and held 16.0 GT/s under load with no link event. Do not try
to get there by asking RM to retrain upward — that is the retrain #979 saw
drop this same enclosure + card pairing.

## Cross-references

- tinygrad discussion #18213 — the earlier field notes and this addendum:
  https://github.com/tinygrad/tinygrad/discussions/18213
- NVIDIA/open-gpu-kernel-modules#979 — the Linux hard-lock thread on the same
  enclosure family: https://github.com/NVIDIA/open-gpu-kernel-modules/issues/979
- tinygrad #15638, #15813, #15843, #15605 — the macOS Intel-dock failure
  reports the Ada pin resolves
- This repository's README, "Field notes: NVIDIA cards behind Intel Thunderbolt 5 docks"
