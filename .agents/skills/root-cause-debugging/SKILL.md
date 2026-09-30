---
name: root-cause-debugging
description: Use when hunting a bug to its root cause in TinyGPU — the dext, the server, the wire protocol, or a client symptom. Reproduce, isolate, explain, fix the cause, verify; never patch symptoms.
---

# Root-cause debugging (TinyGPU x1476 fork)

A fix without a proven root cause is a coin flip that ships. Every bug
gets the same discipline: **reproduce, isolate, explain, fix the cause,
verify the explanation**. The explanation must predict the fix — if it
does not, the cause is still unknown.

## 1. Reproduce before you touch code

- Get a deterministic repro (or the closest observable stand-in) and
  write it down: exact commands, expected vs actual, how often it fires.
- Hardware-dependent failures record the setup per `tinygpu-field-notes`:
  machines, cards (PCI ids), enclosure/bridge chip, link as trained,
  macOS and tinygrad versions, which `log stream` observers were open.
- No repro is itself a finding: characterize what varies between good
  and bad runs (link state, card index, boot order) and shrink that
  space first. Never start "fixing" what you cannot yet observe.

## 2. Isolate, then explain

- List hypotheses, rank them by fit to the evidence, and test them one
  at a time — one change per experiment, so a result stays attributable.
- Instrument before you guess: `log stream` on `apciec`, `DART`,
  `tinygpu`, the server's `PROBE`/`PING` round trips, wire-level traces.
  A printf that distinguishes two hypotheses beats ten speculative edits.
- Bisect the space that is cheapest: commits (`git bisect`), then
  configuration (one card vs two, dock vs direct, SIP-off builds), then
  the input set (binary-search which operation poisons which later one —
  the polluter-search pattern).
- The root cause is a mechanism, not a correlation. "It stopped after
  the retry loop" is not a cause; "the server answers `RESET` only when
  the device is usable again, and the client assumed readiness" is.

## 3. Know this codebase's fault lines

Where the C lifetime and blocking bugs of #2 and #3 class live:

- **Ownership in `server.c`**: buffer lifetimes across unix-socket
  calls, `MAP_BAR`/`MMIO_*`/`SYSMEM_*` spans outliving their mapping,
  error paths that skip a free or double-release.
- **Blocking and readiness**: `RESET` completing is not readiness;
  clients must re-`PROBE`. Sockets that block on a dead device look
  like hangs, not errors.
- **Matching and topology**: display-class matching (a 3D-controller
  card still needs a driver instance), and the `usb4:<n>` bus trap —
  client logic matching `pcibus == "usb4"` silently misses card 2+.
- **DART/IOMMU mapping**: wrong aperture or stale mappings present as
  corruption far from their cause.
- **Signing and entitlements**: Release vs NoSIP entitlement sets do
  not mix; "works ad-hoc, fails Developer ID" is a signing delta, not
  a code bug — check the entitlements axis before blaming the dext.

## 4. Fix the cause at the right layer

- Fix where the fault originates (dext, server, or client), not where
  the symptom surfaces. A retry loop over a lifetime bug, a widened
  timeout over a readiness bug, a re-match over a topology bug: all
  symptom patches, forbidden here.
- Smallest diff that removes the mechanism; follow the repo's commit
  convention and never rewrite the preserved upstream history.
- When the fix changes behavior a client can observe, say so in the
  commit message and the wire-protocol notes (the protocol is frozen;
  1.1 clients must keep working).

## 5. Verify and record

- The original repro passes, and the explanation from step 2 accounts
  for both the old failure and the new pass. A green run with no
  explanation is not done.
- Verify on the checks this host can honestly run (`bash -n` for
  scripts; macOS builds only on macOS with Xcode) and label what was
  and was not actually run — never overclaim.
- Hardware-observed behavior lands in field notes (see
  `tinygpu-field-notes`): measured facts, validated vs not, dated.
- The commit message states the cause first, then the change; link the
  issue the bug lives in (e.g. `Refs #2`).

## Red flags

- Editing code before a repro or a characterized failure exists.
- "It passes now" offered as proof, with no mechanism named.
- Two hypotheses tested in one change.
- A fix whose explanation would also "explain" three other bugs.
- Claiming macOS validation from a Linux checkout.
