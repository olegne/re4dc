# P4 serial capture: diagnostic branch and hardware test protocol

Checkpoint: 2026-10-09. Branch: `diag/p4-serial-capture` in `olegne/re4dc`.

## Status and scope

This is a documentation-only starting point. It does not enable serial output,
remote input, a bot, or a new play build. No performance improvement or physical
acceptance is claimed. Runtime and build defaults are unchanged.

The fork and upstream `dreamcast-port` were both at
`0770815fb05c0541f00e340713074221c321781b` when this branch was created. That commit
updates the README; the inherited runtime includes `254eab36`. Pin exact source,
toolchain, resolved build flags, asset identities and executable hashes in each
test record. A source commit alone does not identify a runnable asset fixture.

Keep the fork's `dreamcast-port` as the upstream tracking branch. Develop this
diagnostic change here and put each later optimization on its own `perf/...`
branch. No upstream PR is opened at this checkpoint. A later PR must contain a
focused change and reproducible evidence, with the original license and credits.

Read [AGENTS.md](../../../AGENTS.md), [CLAUDE.md](../../../CLAUDE.md) and the
[play-build checklist](D367_PLAY_BUILD_CHECKLIST.md) before runtime work. The
upstream shared `re4-dreamcast-d367` skill is not included in this repository;
do not assume that its external workspace, private inputs or tools are present
in a new contributor environment. This checkpoint does not replace upstream
source-preservation, memory, movie or release gates.

## Capture path and current source behavior

The current laboratory reader uses a GUITION JC-ESP32P4-M3-DEV:

- Dreamcast to P4: UART receive, 115200 baud, 8N1.
- P4 USB1/CH340C to PC: 230400 baud, 8N1.
- Reader mode is receive-only. Do not confuse it with a separate 57600-baud
  bidirectional dcload bridge. Record the actual firmware hash and baud rates.
- Keep the GDEMU storage interface passive; this procedure does not reset the
  console or write to its card. No credentials belong in capture firmware.

The hardware reader has received console output from another application.
That does not establish RE4 capture: at the pinned source,
`game/platform/mem.cpp` owns a 64 KiB log ring, and `game/platform/fault.cpp`
selects the `re4ring` dbgio handler and clears `re4dc_log_console`.
The handler's read path returns -1; it is not a serial command receiver.
Turning `re4dc_log_console` back on can route output back into the ring.

The next implementation should export the existing ring through an independent,
bounded serial sink. Preserve the ring, its writers and the crash screen; avoid
recursive stdout and blocking UART work in an interrupt handler. Define explicit
wrap/overrun accounting and a maximum byte/time budget per drain. Measure actual
cost instead of assuming that asynchronous capture is free. Include build,
sequence, room/generation, game tick and monotonic clock identities where available.

Fault paths can disable interrupts and halt. A normal drain thread is insufficient
for the final fault report: qualify a bounded polling fallback separately, while
retaining the existing on-screen report. Do not add reset or reboot behavior.

## Evidence collected by the PC

Preserve the raw received byte stream and a decoded text copy. Record session
identity, firmware identity, port/baud, build, route, reception times and byte
counts. Keep periodic bounded snapshots and a final summary with file hashes.
Distinguish dropped UART bytes, ring overruns and dropped presentation events.
Arrival timestamps on the PC are not game-tick timings and cannot estimate FPS.

Private evidence storage may receive periodic snapshots and a closed-session
archive. Capture must continue locally during a network outage; a remote upload
is successful only after confirmation. Raw evidence and game inputs stay outside
this public fork. For a PR, publish a reviewed result table, commands and only
the diagnostic excerpts needed to reproduce/assess the change.

## A/B procedure

Use [P4_RUN_TEMPLATE.json](P4_RUN_TEMPLATE.json) as a manual evidence record.
Unknown values remain `null`, not zero. Identify whether evidence came from a
host fixture, Flycast, a hardware model or a physical Dreamcast.

1. Build A from the pinned control and B from one candidate, with the same
   toolchain, resolved flags and legal local assets except for the intended
   change. Preserve both artifacts and hashes in separate output directories.
2. Record console revision, boot method, video mode, controller, pacing mode,
   save identity, firmware and the exact start/end of the test route. Reuse the
   same save and distinguish cold boot, loading, warm-up and measured gameplay.
3. Alternate A/B runs, with at least three runs of each for an initial comparison.
   Report all runs and their spread. Extend measurement only if variance leaves
   the proposed gain unresolved. Do not compare different pacing/workload settings.
4. First compare diagnostics off/on to measure capture overhead. Then compare
   the candidate against its matched control. Report FPS and game speed together,
   per-phase costs, PVR timings/waits and memory high-water marks when actually
   available. Missing counters remain unmeasured. `PACE draw_us` covers a loop
   iteration, not an isolated rendering function.
5. Use existing source-state STRICT and required-decision checks as applicable.
   Additional text/rodata/BSS or heap use must pass the inherited memory/movie
   gates, including the relevant H2/s30 case; do not spend unqualified memory
   merely to make logging easier. Record remaining source/visual differences.
6. On physical hardware, check the affected behavior: both camera controls,
   aiming/laser, combat and death, inventory/Examine, audio, loading and room
   transitions. For a hang, retain the last logs plus the existing screen report.
   Host/Flycast success does not establish physical-console acceptance.

## Later route automation

Reuse the platform input adapter and existing fixture scheduler. The current
`padscript.txt` fixture supports button sequences and source-clock/state guards;
it does not provide serial commands or analog walking. Movies have a separate
input path. These are implementation gaps, not already working bot features.

An opt-in virtual controller should include sticks, triggers and buttons, bounded
hold durations, command sequence, received/applied acknowledgements and expected
room/state. A wall-clock lease, STOP and physical override must clear held input
and queued commands even if the game clock pauses or the room changes. Validate
bidirectional transport separately before enabling it on a physical console.

For normal-route acceptance use `DBG_WARP=0`: no position writes, artificial
damage, flags, direct room jumps or invulnerability. Navigation drives ordinary
controls; telemetry may observe state. Track visited, passed, failed and unvisited
room/position/camera/action/context combinations. Timed input alone does not make
AI, RNG or I/O deterministic and cannot prove coverage of every possible state.

## Contribution acceptance

A proposed performance PR should state the problem, exact change, baseline and
candidate identities, reproduction commands, all A/B runs, instrumentation cost,
source/visual checks and physical findings. Separate confirmed observations from
causal hypotheses. Keep diagnostics default-off unless separately justified.
An instrumentation PR may be useful without an FPS gain, but must demonstrate
correctness, bounded cost and useful evidence. This branch has neither result yet.

Next work is the bounded ring-to-serial implementation and its focused tests,
followed by target validation. Do not open a performance PR based solely on
the host collector's tests or this documentation checkpoint.
