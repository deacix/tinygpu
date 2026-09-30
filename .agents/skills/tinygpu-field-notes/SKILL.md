---
name: tinygpu-field-notes
description: Use when recording or updating hardware field notes for TinyGPU — measurements on eGPU enclosures and docks, link state, what is validated vs not, and client traps observed in the field.
---

# TinyGPU field notes convention

Field notes are **measured facts from real hardware**, never predictions.
They live in `README.md` ("Field notes" sections) and `docs/`
(`<topic>-<YYYY-MM>.md`, linked from the README).

## The header block every note carries

- Machines, cards (with PCI ids, e.g. `10de:2b85`), enclosures and bridge
  chips (e.g. Intel TB5 bridge `8086:5786`).
- Software under test: tinygrad version, TinyGPU build/dext version,
  macOS version.
- What observability was open during the measurement (e.g. one
  `log stream` on `apciec`, `DART`, `tinygpu` the whole time).
- Dates of the measurement.

## The status table shape

| Mac | Card | Enclosure | Link as trained | Status |

"Link as trained" states the real negotiated link (e.g. `Gen4 x4 (16 GT/s)
unpinned; Gen1 x4 under the pin`), never the link marketing promises.

## Rules

- **Where something is not measured, say so.** "Validated" and "not
  validated" are explicit words; never overclaim.
- Every claim names the exact build/version it rides on. Facts about
  GSP-RM, the card or macOS are called out separately from facts about a
  tinygrad version.
- Client traps are recorded with observed behavior, root cause and fix —
  e.g. tinygrad names a second card's bus `usb4:1`, so client logic that
  matches `pcibus == "usb4"` silently misses every card past the first
  (observed: a card ran a day on the host-memory launch path at half
  speed).
- Benchmarks carry the workload, units and conditions
  (e.g. `tinygrad.llm` tok/s on the same dock), and a caveat when a wheel
  ships missing kernels.
- Link upstream threads by number (tinygrad issues/PRs) when the note
  relates to one; state plainly when an upstream PR was closed for policy,
  not technical, reasons.

## Where a note goes

- A cross-cutting measurement spanning setups: `docs/<topic>-<YYYY-MM>.md`
  plus a README link.
- A card/dock-specific lesson: a README field-notes section under the
  card's heading (AD103/GB202/…).
- An update to an existing note: append with the new date; never rewrite
  what earlier measurements said.