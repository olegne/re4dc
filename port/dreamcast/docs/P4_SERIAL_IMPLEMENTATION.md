# Bounded RAM-log export to the P4 reader

Checkpoint 2026-10-09, `diag/p4-serial-capture`. Implementation base:
`acb9289f198c4c7e4486ce86917605ed395c0059`. This is diagnostic source,
not a qualified play release or a measured performance improvement.

## Switch and ownership

`SERIAL_LOG=0` is the default. `serial_log.mk` excludes the new object when off
and generates an include for `serial_log`, `fault`, `os` and `mem`. The generator
updates its file only when the switch or Git identity changes, avoiding a stale
incremental switch. Still use a fresh OBJDIR for every recipe as upstream requires.
The enabled banner contains the Git revision plus `-dirty` when applicable;
this is not a substitute for the executable's SHA-256.

Add `SERIAL_LOG=1` to the existing `build-r21.sh` invocation with its current play
or trace overrides. Do not replace that recipe with the isolated checks below.
`resolved-knobs.txt` must include this explicitly supplied switch. Diagnostics
must be compared off/on with all other source, asset and pacing inputs matched.

Boot through a non-serial loader, such as the qualified GDEMU image. The exporter
refuses serial dcload and an unavailable RAM logger. Do not combine it with GDB,
a serial SD adapter or another UART writer: it cannot discover every SCIF owner.
It changes SCIF to 115200, 8N1, no flow control during initialization. The P4 is
receive-only for this step. There are no control commands, resets or card writes.

## Normal operation and limits

- Reuse the existing 64 KiB RAM ring. No second log buffer or per-frame allocation.
- The existing producer's IRQ-atomic path is enabled for serial builds. Without
  it a preempted `head++` can publish an older head after another writer. This
  prevents that race but adds interrupt latency for each log append; qualify it.
- One task uses an explicit 4,096-byte aligned stack, priority 8 and disabled TLS.
  KOS still allocates its thread record. A thread-creation failure logs to RAM
  and leaves gameplay running without export.
- Each IRQ-protected poll inspects SCFSR/SCFDR and writes at most 16 currently
  free FIFO slots. The worker does not write to the ring, stdout or dbgio and
  does not call `scif_write`, `scif_write_buffer` or `scif_flush`.
- After a control notice, allow up to 64 raw bytes before another notice. This
  prevents sustained overruns from replacing all useful logs with loss notices.
- The requested sleep is 1 ms, not a guaranteed 1 kHz schedule. Pinned KOS uses
  a 100 Hz default timer; with only one wake per 10 ms, total output is at most
  about 1,600 bytes/s before notice overhead. Other scheduling points may change
  this. The line rate is not the achieved drain rate. No global scheduler change
  is made to increase logging bandwidth.
- Ring overflow skips older unsent bytes. `lost` saturates at UINT32_MAX; other
  counters wrap as uint32_t. Producing 2^32 bytes between polls is unsupported.
  UART acceptance is not receiver acknowledgement. A disconnected cable or P4
  receiver overflow cannot be detected by this TX-only implementation.

The wire contains existing raw log bytes and newline-delimited `[RE4SER ...]`
notices. `begin` identifies build/baud/burst. `stats` samples milliseconds, head,
sent raw bytes, backlog, loss, polls, busy polls, maximum observed poll duration
and stage. Periodic stats wait for a source newline and at least one second;
they are not guaranteed during an unterminated record. `max_poll_us` includes
preemption and scheduling delay and is not CPU time or FPS.

A `loss` notice's `observed_bytes` and `sampled_next` describe the sample when the
notice was created. More bytes can be overwritten while that notice is being
transmitted. Notices are not exact framing of every wire gap; records can be
partial and cannot be reconstructed as lossless output. Preserve the raw stream
and distinguish these cumulative counters from P4/PC reception loss.

## Terminal faults

The existing fault, source HALT and OSPanic paths call an emergency drain after
they have already disabled interrupts and chosen to halt. It stops the normal
worker and retains at most the latest 2,048 **unsent** bytes. Older pending bytes
count as lost. It attempts a header and this tail until either 200,000 us elapse,
1,048,576 poll attempts occur, or all retained bytes are queued to the FIFO.
There is no sleep, flush, receiver ACK, retry reset or reboot.

The hardware timer can roll over while its IRQ is disabled; an elapsed-time jump
may stop the attempt early. The attempt-count limit also terminates a frozen
clock. Full delivery is not promised, and the screen/halt remains the fallback.
Only existing RAM log bytes are exported; extra on-screen thread/backtrace
information is not automatically serialized. The regular worker also cannot
capture an IRQ-disabled deadlock that never reaches a terminal handler.

## Checks completed here

47 host tests passed:

```sh
python3 -m unittest discover -s port/dreamcast/tests -p 'test_serial_log_*.py' -v
```

These include ring wrap/overrun, loss saturation, partial FIFO acceptance,
register count/flag handling, generated configuration/identity, and 12 tests
compiling the actual adapter with fake KOS and mapped SCIF register addresses.
The latter cover startup guards, init-once/thread failure, bounded bursts,
continuous-overrun progress and both emergency termination bounds. They model
control flow, not physical UART transmission or SH-4 interrupt timing.

Cross-compiler: SH-ELF GCC 15.1.0; KOS headers at
`804b3195ebd1a06a27cc2b3a5eacf7a2429040a3` (toolchain.lock). The compiler archive
was obtained from drpaneas/dreamcast-toolchain-builds, release
`gcc15.1.0-kos2.2.1`, SHA-256
`36ee8b174331f53996990327de8df77ff662041989bbafab9e68572383d03b41`.
This compiler is an isolated check, not a claim of the accepted release compiler.

`serial_log.cpp`, `fault.cpp`, `os.cpp`, `mem.cpp` compiled both directly and
through the project's actual Makefile with `SERIAL_LOG=1 CRASH_SCREEN=1 NO_EH=1
GAME_OPT=-Os`. Only those four object targets were built. The Makefile resolved
the generated serial header on all four targets; no full ELF was linked.

For the isolated size comparison the common flags were `-std=gnu++20 -Wall
-Wextra -Os -ml -m4-single-only -D_arch_dreamcast -D_arch_sub_pristine
-fno-exceptions -fno-rtti -fstack-usage`, with the pinned KOS/platform includes.
Resident budget defines were sound 393216, core 1360608, option 149920, player
869728, weapon 275424 and KOS reserve 0; no ARENA_FIT. Both arms used identical
flags. Enabled build ID was `isolated-check`. GNU `size` reported:

| Object | Off text/data/BSS, bytes | On text/data/BSS, bytes |
| --- | --- | --- |
| serial_log | excluded (empty if compiled) | 2106 / 1 / 4400 |
| fault | 810 / 36 / 0 | 846 / 36 / 0 |
| os | 5756 / 4 / 1076 | 5768 / 4 / 1076 |
| mem | 1211 / 36 / 196768 | 1227 / 36 / 196768 |

The three existing knob-off objects' loadable bytes (`objcopy -O binary`) match
objects compiled from the base source with these same flags. This is an isolated
object comparison, not linked-image or overlay identity. The enabled object
sum grows by 6,571 bytes, before linker layout/alignment, pulled dependencies
and KOS runtime allocations. Do not treat it as final heap usage.

Implementation review used pinned KOS `kernel/arch/dreamcast/hardware/scif.c`,
`kernel/thread/thread.c` and the SH7750 SCIF register definitions. The standard
KOS serial functions contain polling/flush behavior, which is why the drain
uses bounded register access instead.

## Pending before a console test image

The current environment has the public repository, pinned KOS headers and the
cross-compiler. It does not have the recipe's private generated actor/VMU headers,
matched disc/route/movie fixtures or a built, patched KOS library. A GameCube ISO
or the public sources alone are not that complete build fixture.

1. Restore those inputs from the current working build environment and pin their
   hashes. Build separate off/on images with the accepted recipe and overrides.
2. Run the applicable source STRICT/required-decision and alignment checks. Pass
   H2 through r100 s30 with 340/340 movie frames and report `heap_before`; new
   text/BSS and the thread allocation may reduce an already constrained arena.
3. Measure off/on cost, actual UART throughput and loss on the P4; verify a
   controlled terminal-fault tail without replacing the existing crash screen.
4. Save private capture evidence and fill `P4_RUN_TEMPLATE.json`. Qualify this
   transport before adding bidirectional input or submitting an upstream PR.

No FPS gain, console acceptance, complete crash dump or bot coverage is claimed.
