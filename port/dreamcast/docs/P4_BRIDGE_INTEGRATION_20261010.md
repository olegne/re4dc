# Bridge integration checkpoint, 2026-10-10

The diagnostic branch incorporates upstream `dreamcast-port` through
`f7c5c31fefc69d5aa21916c82179ca4457e14711`. Upstream gameplay changes are kept.
Our additional runtime work exports the existing RAM log and the first captured
PVR stop state to the receive-only P4 collector. It does not fix the bridge hang.

`SERIAL_LOG=1` adds `[RE4STOP ...]` records for the first MISSING and for the
existing 30-second watchdog. Records contain the reason, stage, UI frame, PVR
counters/registers, ASIC status and available latch rows. The MISSING snapshot
is taken before later logging or sleeping; records are appended after restoring
the original interrupt state. The watchdog records its current state only when
there was no first MISSING. The report uses no heap allocation or direct UART
write. Each line fits the existing formatter and the report is below 1.1 KiB.
The original screen, halt behavior and thread/backtrace report remain necessary.

The disabled hook has no state, strings or calls. Hook placement preserves the
physical line numbers in crash_screen.cpp, including its existing __LINE__
diagnostic literals. Both builds use fresh object directories. The generated
serial header now applies to crash_screen.o as well as the four prior objects.

The cast-only Ganado adapter no longer requires the unused historical
ganado874_runtime.h. The original and comparison adapters still require the
real header. No generated data or SDK header is replaced by a stub.

## Recovered inputs and reproducible build

The five real generated headers were recovered from the previous private R02
rebuild archive. The immutable disc donor is the official d74b8ec8 GDEMU test
archive, SHA-256
`1fec9dd0d5fda4f5f7910de351ce58a327766236b0462b5540b5df8c4ee617a8`.
Its texture pack is unchanged, SHA-256
`d87983e17e3af9f8d7233918becac866fc1c1552036f07dfd821a099feae38a6`.

The donor does not include the newly staged r119/r118/r117 content. The upstream
disc-presence guard keeps these rooms unavailable. Incorporating their source
does not make their private assets available. Retain the donor payload, replace
1ST_READ.BIN and every overlay from the same build, and do not ship warp or
padscript files. SBB_STUB=1 is required for this donor's omitted stream banks.

Run `tools/d367/build-p4-bridge.sh` with ASSETS, a new absolute BUILD_ROOT,
RE4DC_KOS_BASE, RE4DC_KOS_CC_BASE and the other kos-env.sh paths configured.
It produces A_SERIAL_OFF and B_SERIAL_ON with the current play recipe and
matching overrides. PVR_READY_STRICT=1 and PVR_LATCH=2 are diagnostic choices
in both arms; recovery and extra TA-bin diagnostics are disabled. This pair
qualifies the serial transport on current source, rather than byte identity
with the old R02 image or the public donor executable.

The SDK is pinned to toolchain.lock KOS with the three PVR patches. The restored
compiler is GCC 15.2.0, not the previous isolated GCC 15.1.0 check. Preserve the
actual compiler version, resolved knobs, ELF and overlay hashes in private
build evidence. A full link, real-GDI boot/New Game, alignment and the r100 s30
340/340 heap gate are still required before describing these as ready images.

## Physical capture

Use the same save and route for A and B, start PC capture before console boot,
and reproduce the r108-to-r109 bridge transition. The Dreamcast UART is 115200
8N1; the existing P4-to-PC CH340 stream is 230400. A may have no serial game
records. In B check RE4SER identity and loss counters, retain raw bytes, and
photograph the whole stop screen. Wait for the watchdog and allow another
15 seconds for draining before stopping capture. The collector does not send
controller commands or change the console.

No physical throughput, bridge correction, console FPS gain, complete fault
delivery or upstream acceptance is claimed by this checkpoint.

Host validation at this checkpoint: all 48 `test_serial_*.py` tests passed,
including six sanitizer builds of the real stop hooks (serial off/on with
latch 0/1/2). `test_crash_missing_snapshot.py` passed with asynchronous PVR
present both absent and present. `test_crash_wait_report.py` passed when run
directly; it uses main() and is not discovered by unittest. These are host
control-flow checks, not physical Dreamcast timing or P4 delivery tests.
