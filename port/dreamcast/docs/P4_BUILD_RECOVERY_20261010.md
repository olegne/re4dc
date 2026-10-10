# P4 serial build recovery — 2026-10-10

## Confirmed recovery

The previous scratch build environment was removed by workspace maintenance.
Source remains in `diag/p4-serial-capture`; the implementation checkpoint is
`a489cec489075c34699b4fa4e7f76bdced93a41b`, based on upstream
`0770815fb05c0541f00e340713074221c321781b`.

Recovered the existing private archive `RE4_NOIS_R02_PRIVATE_REBUILD.zip`.
Archive bytes: 39,167,952. SHA-256:
`d72fd922ed598210056a5e9fc89ea8229de527a4570e78b32f50c85d9608cb87`.
All 118 ZIP entries passed CRC verification. The five compilation inputs below
were extracted successfully; no private game data is committed by this note.

| Input | Bytes | SHA-256 |
| --- | ---: | --- |
| leon4k_runtime.h | 342012 | 5a9a70a779583f63788e488ddca2fdf0a7d87b4972c9f1e4fe74410bd766719c |
| leon_hair_runs.h | 52619 | d4d21572888a87f29b4fb1ea260e40b63547361dac5de1e44c08dc9477c39cd7 |
| ganado_cast_runtime.h | 379184 | 64cf544d1d0109f2cdc6acc644047ce18c260de02860b4a3fa668e50e71a962f |
| vmu_dialog_english.inc | 32038 | be083f0d43daa7fcba93f1ea4f438105fb85aecee6979071ea86d86545646ef7 |
| ganado_source_extras.h | 60280 | 89805197a8b6ab2d5da573c31bf02113bb3c1828593f3772b50b21df713b1243 |

The earlier request for the user to locate these four principal headers on
their PC was premature. They already existed in the saved R02 archive.
Recovery does not establish compatibility with all current build options.

## Remaining work

1. Restore the pinned SH-4 compiler and patched KOS environment using the saved
   recipes/manifests. The archive contains SDK records; do not assume it is a
   complete prebuilt SDK.
2. Check actual header dependencies against the current selected build profile.
   In particular, distinguish the unconditional `ganado874_runtime.h`
   Makefile prerequisite from the cast profile selected by the play recipe.
   Never satisfy a dependency with a dummy header.
3. Match the disc content, overlays and movie/route fixtures to that profile.
   The R02 disc content predates newer weapon and moving-object assets.
4. Produce matched `SERIAL_LOG=0` and `SERIAL_LOG=1` full builds, using fresh
   object directories, and record their configuration and hashes.
5. Run the inherited memory/movie/source checks before assembling deliverable
   GDI images. Physical P4 capture and its performance cost remain unvalidated.

A finished GDI contains useful converted runtime disc content, but is not a
replacement for the full source, generated C headers and SDK used to compile.
Do not state that the image is useless for recovery, or that it alone recreates
the build environment.

## User workflow

Continue delivering ready-to-copy GDI packages. A full compiler installation
on the user's PC is optional. The minimal hardware-test setup remains the
working Dreamcast/OpenMenu, P4 serial bridge and PC log collector.

If a local build environment is requested, assemble a versioned WSL setup from
the verified pins, patched SDK, generated headers and disc data first; verify
the procedure before presenting it as a one-command installer.

No new ELF/GDI, full link, emulated play acceptance, physical acceptance or FPS
gain was produced in this recovery step. No upstream PR was opened.
