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
- `PING` returns a version so a client can tell this build from upstream's.

The wire protocol is otherwise unchanged; tinygrad 0.14.0 talks to it as is.

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

## License

MIT, as upstream (`LICENSE`, Copyright (c) 2024, the tiny corp).
