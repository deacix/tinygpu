# Two-card IMPORT_SYSMEM_FD smoke on the Mac mini — server 1.2 read-back

Field measurement, 2026-10-02, 17:05 UTC. The short form is in the README's
field notes; this page carries the facts. Measured facts only — where
something was not recorded or not validated, the page says so.

## Setup

| Item          | Value                                                                                                   |
| ------------- | ------------------------------------------------------------------------------------------------------- |
| Host          | Degensoft Office Mac Mini: Apple M4 Pro, macOS 27.0 (26A428), SIP disabled                               |
| Cards         | three NVIDIA GeForce RTX 5090 eGPUs (`10de:2b85`); the smoke used cards 0 and 1                          |
| Enclosures    | not recorded                                                                                             |
| Link state    | not recorded                                                                                             |
| Driver        | `systemextensionsctl` lists `org.tinygrad.tinygpu.driver2 (1.1.0/5) [activated enabled]` (fork.3's dext) |
| Server binary | built from `main@e0abbde` with the Command Line Tools only (see below)                                   |
| Observability | not recorded                                                                                             |
| When          | 2026-10-02, 17:05 UTC                                                                                    |

| Mac                            | Card                                       | Enclosure    | Link as trained | Status                                     |
| ------------------------------ | ------------------------------------------ | ------------ | --------------- | ------------------------------------------ |
| Degensoft Office Mac Mini (M4 Pro) | 2 of 3 × GeForce RTX 5090 `10de:2b85` (cards 0, 1) | not recorded | not recorded    | `import ok`, exit 0 (validated list below) |

## The server binary

Built from `main@e0abbde` with the Command Line Tools only, since that Mac
has no Xcode:

- `clang -std=gnu11 -O2 -c Shared/server.c`;
- `swiftc -O -parse-as-library -import-objc-header Shared/TinyGPU-Bridging-Header.h Shared/TinyGPUApp.swift Shared/TinyGPUCLIRunner.swift server.o -framework IOKit`;
- ad-hoc signed with `installer/macOS/macOS.entitlements`;
- SHA-256 `35670474242e0f4b7a4ce53a3a62f987163a97669f640e129739db181b02da81`.

## Isolation

The installed app (1.1.0, server 1.1) and its servers were left alone. The
engine serving on the cards was stopped first. The smoke ran its own two
servers on fresh sockets (`TMPDIR=<new dir>`).

## Command

`python3 tests/import_sysmem_smoke.py --cards 0,1 --app <that binary>`
(Python 3.9.6). Output `import ok`, exit 0.

## Validated

- PING reports 1.2 on both servers;
- `MAP_SYSMEM_FD` maps 2 MiB on card 0;
- `IMPORT_SYSMEM_FD` on card 1 returns an IOVA table covering the region and
  leaves the bytes untouched;
- RESET is refused while the import is live;
- the size boundaries: 16 KiB succeeds; no fd, 4 KiB, a non-4-KiB multiple
  and a size past the region are refused;
- an 8 MiB region comes back in at most 32 segments.

## Not validated

- `--allow-reset` (the mapping released on disconnect, then a reset);
- the Xcode-built release binary (this was a CLT build of the same sources);
- dext build 6 (that Mac runs build 5);
- a GPU actually reading or writing through the imported mapping (that is
  Legwork's card-bridge `bridgebench`, rows 2 to 4 of its runbook);
- enclosure and link state (not recorded).