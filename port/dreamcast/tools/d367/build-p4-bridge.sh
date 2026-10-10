#!/usr/bin/env bash
# Matched, playable bridge diagnostic builds. All outputs stay outside the repo.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../../../.." && pwd)
: "${ASSETS:?directory of the five real generated headers}"
: "${BUILD_ROOT:?new absolute output directory}"
: "${RE4DC_KOS_BASE:?patched KOS from toolchain.lock}"
: "${RE4DC_KOS_CC_BASE:?SH-ELF compiler installation}"
case "$BUILD_ROOT" in /*) ;; *) echo 'BUILD_ROOT must be absolute' >&2; exit 2 ;; esac
if [ -e "$BUILD_ROOT" ]; then
    echo 'BUILD_ROOT already exists; choose a new directory for fresh objects' >&2
    exit 2
fi
for header in leon4k_runtime.h leon_hair_runs.h ganado_cast_runtime.h ganado_source_extras.h vmu_dialog_english.inc; do
    test -s "$ASSETS/$header" || { echo "Missing real input: $header" >&2; exit 2; }
done
mkdir -p "$BUILD_ROOT"
git -C "$ROOT" rev-parse HEAD > "$BUILD_ROOT/source-commit.txt"
git -C "$ROOT" status --porcelain > "$BUILD_ROOT/source-status.txt"
if [ -s "$BUILD_ROOT/source-status.txt" ]; then
    echo 'Commit the source checkpoint before producing identified images' >&2
    exit 2
fi
COMMON=(
  DBG_WARP=0 QUALITY_PICKER=0 ARENA_FIT_KOS_BYTES=147456
  PACE_MODE=fast PACE_DEBUG=1 LOGIC_TRACE=0 GAME_DECISION_TRACE=0
  ACTOR_TRANSACTION_DIAG=0 GAME_PWC_DIAG=1 PC_SAMPLER=0
  ROUTE_CH13=1 ROUTE_CH21=1 ACT_CAP=0 PS2_INTERIOR_ACTORS=2
  GAME_ATLIST_OVERFLOW=1 GAME_ATLIST_512=1 LEON_NATIVE_PIPE=0 LEON_FACE_LAZY=0
  NATIVE_LASER=1 ACTOR_GANADO_SOURCE_LIGHT=0 PRIM_CAP_R10B=327680 SBB_STUB=1
  PVR_READY_STRICT=1 PVR_LATCH=2 PVR_RECOVER=0 TA_BIN_DIAG=0
)
printf '%s\n' "${COMMON[@]}" > "$BUILD_ROOT/common-knobs.txt"
for arm in A_SERIAL_OFF B_SERIAL_ON; do
    enabled=0
    [ "$arm" != B_SERIAL_ON ] || enabled=1
    mkdir -p "$BUILD_ROOT/$arm"
    ASSETS="$ASSETS" OBJDIR="$BUILD_ROOT/$arm/obj" OUT="$BUILD_ROOT/$arm/out" \
      bash "$ROOT/port/dreamcast/tools/d367/build-r21.sh" \
      "${COMMON[@]}" "SERIAL_LOG=$enabled" 2>&1 | tee "$BUILD_ROOT/$arm/build.log"
    test -s "$BUILD_ROOT/$arm/out/re4dc-game.elf"
    sha256sum "$BUILD_ROOT/$arm/out/re4dc-game.elf" > "$BUILD_ROOT/$arm/elf.sha256"
done
