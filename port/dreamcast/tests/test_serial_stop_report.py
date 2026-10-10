"""Compile the actual first-failure capture and bounded serial report hooks."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
PLATFORM = ROOT / "port/dreamcast/game/platform"


def function(source, signature):
    start = source.index(signature)
    pos = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[pos] == "{") - (source[pos] == "}")
        pos += 1
    return source[start:pos]


class SerialStopReport(unittest.TestCase):
    def test_capture_once_bounded_and_after_irq_restore(self):
        source = (PLATFORM / "crash_screen.cpp").read_text()
        start = source.index("struct MissingSnapshot {")
        end = source.index("void capture_missing(", start)
        self.assertIn("RE4DC_SERIAL_STOP_WATCHDOG_EMIT()", function(source, "void* watchdog("))
        code = r'''
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdarg>
#include <cstdint>
#include <string>
#include <vector>
struct pvr_stats_t { unsigned frame_count, vbl_count; };
unsigned long re4dc_stage = 0x1234abcd;
volatile int g_shown;
bool initialized = true, irq_off;
unsigned frames = 12, vbl = 100, reads, restores, latch_reads;
uint32_t asic[3] = {0x12345678, 0x9abcdef0, 0x00000005};
#define ASIC_ACK_A (&asic[0])
#define ASIC_ACK_B (&asic[1])
#define ASIC_ACK_C (&asic[2])
std::vector<std::string> records;
int irq_disable() { assert(!irq_off); irq_off = true; return 37; }
void irq_restore(int old) { assert(old == 37 && irq_off); irq_off = false; ++restores; }
unsigned re4dc_ui_frame() { return 44; }
int pvr_get_stats(pvr_stats_t* p) { assert(irq_off); p->frame_count = frames; p->vbl_count = vbl; return initialized ? 0 : -1; }
int pvr_check_ready() { assert(initialized && irq_off); return -1; }
extern "C" int pvr_present_pending() { assert(irq_off); return 1; }
extern "C" int re4dc_pvr_latch_line(unsigned n, char* out, unsigned size) {
    assert(irq_off && initialized); ++latch_reads;
    // Exercise the maximum captured row length, including an unterminated row.
    std::memset(out, 'A' + n, size); return 1;
}
enum { PVR_TA_VERTBUF_START = 1, PVR_TA_VERTBUF_POS, PVR_TA_VERTBUF_END,
       PVR_TA_OPB_START, PVR_TA_OPB_POS, PVR_TA_OPB_END,
       PVR_ISP_VERTBUF_ADDR, PVR_TA_OPB_INIT };
unsigned read_pvr(unsigned n) { assert(initialized && irq_off); ++reads; return n * 0x100; }
#define PVR_GET(n) read_pvr(n)
void re4dc_log(const char* fmt, ...) {
    assert(!irq_off); // Reporter must append after restoring normal caller IRQ state.
    char row[256]; va_list ap; va_start(ap, fmt);
    int count = vsnprintf(row, sizeof(row), fmt, ap); va_end(ap);
    assert(count >= 0 && count < int(sizeof(row)));
    records.emplace_back(row);
}
''' + source[start:end] + function(source, "void capture_missing(") + r'''
void assert_bound() {
    unsigned bytes = 0;
    for (const auto& r: records) { assert(r.size() < 256); bytes += r.size(); }
    assert(bytes < 1100);
}
int main() {
    capture_missing("native stream completion fence failed");
    assert(g_missing.valid && g_missing.pvr_valid && g_missing.ui == 44);
    assert(g_missing.frames == 12 && g_missing.vbl == 100 && g_missing.pending == 1);
    assert(g_missing.vtx[1] == 0x200 && g_missing.opb[1] == 0x500 && g_missing.isp == 0x700);
    assert(g_missing.opb_init == 0x800 && g_missing.asic[2] == 5 && reads == 8);
    unsigned size = records.size(), initial_latches = latch_reads;
#if RE4DC_SERIAL_LOG
    assert(size == 4 + (RE4DC_PVR_LATCH ? (RE4DC_PVR_LATCH == 1 ? 4 : 6) : 0));
    assert(records[0].find("kind=missing") != std::string::npos);
    assert(records[0].find("stage=1234abcd ui=44") != std::string::npos);
    assert(records[1].find("frames=12 vbl=100 pending=1 ta_ready=-1") != std::string::npos);
    assert(records[2].find("opb_init=00000800") != std::string::npos);
    assert(records[3].find("c=00000005") != std::string::npos);
    assert_bound();
#else
    assert(size == 0);
#endif
    frames = 99; vbl = 800; capture_missing("later failure");
    assert(records.size() == size && reads == 8 && latch_reads == initial_latches && restores == 2);
    assert(g_missing.frames == 12 && std::strcmp(g_missing.reason, "native stream completion fence failed") == 0);
    RE4DC_SERIAL_STOP_WATCHDOG_EMIT(); // A MISSING already exported the immutable snapshot.
    assert(records.size() == size && reads == 8);

    records.clear(); g_missing = {}; initialized = false; capture_missing(nullptr);
    assert(g_missing.valid && !g_missing.pvr_valid && reads == 8);
#if RE4DC_SERIAL_LOG
    assert(records.size() == 2 && records[0].find("reason=unknown") != std::string::npos);
    assert(records[1] == "[RE4STOP pvr valid=0]\n");
#else
    assert(records.empty());
#endif
    records.clear(); g_missing = {}; initialized = true;
    char name[256]; std::memset(name, 'x', sizeof(name)); name[2] = '\n'; name[3] = '\r'; name[255] = 0;
    capture_missing(name);
    assert(std::strlen(g_missing.reason) == 79 && reads == 16);
#if RE4DC_SERIAL_LOG
    assert(records[0].find("reason=xx  xxx") != std::string::npos);
    assert(records[0].find('\n') == records[0].size() - 1);
    assert_bound();
    records.clear();
    MissingSnapshot largest = g_missing;
    largest.ui = largest.frames = largest.vbl = largest.isp = largest.opb_init = UINT32_MAX;
    largest.pending = largest.ta_ready = INT32_MIN;
    for (unsigned i = 0; i < 3; ++i) largest.vtx[i] = largest.opb[i] = largest.asic[i] = UINT32_MAX;
    serial_stop_snapshot("watchdog", largest, ~0ul);
    assert_bound(); // Maximum-width integers, reason and all six latch rows.
#endif

    records.clear(); g_missing = {}; unsigned before = reads;
    RE4DC_SERIAL_STOP_WATCHDOG_EMIT();
    assert(!g_missing.valid); // A watchdog report must not publish or overwrite first-failure state.
#if RE4DC_SERIAL_LOG
    assert(reads == before + 8 && records[0].find("kind=watchdog") != std::string::npos);
    assert(records[1].find("frames=99 vbl=800") != std::string::npos);
    assert_bound();
#else
    assert(reads == before && records.empty());
#endif
    size = records.size(); before = reads;
    RE4DC_SERIAL_STOP_WATCHDOG_EMIT();
    assert(records.size() == size && reads == before); // One report, even on repeated watchdog calls.
#if RE4DC_SERIAL_LOG
    g_serial_watchdog_reported = false; g_shown = 1;
    RE4DC_SERIAL_STOP_WATCHDOG_EMIT();
    assert(records.size() == size && reads == before);
#endif
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            (work / "check.cpp").write_text(code)
            for serial in (0, 1):
                for latch in (0, 1, 2):
                    with self.subTest(serial=serial, latch=latch):
                        subprocess.run([
                            "g++", "-std=c++17", "-fsanitize=address,undefined",
                            f"-DRE4DC_SERIAL_LOG={serial}", f"-DRE4DC_PVR_LATCH={latch}",
                            "-I", str(PLATFORM / "include"), str(work / "check.cpp"),
                            "-o", str(work / "check"),
                        ], check=True)
                        # This container restricts procfs task inspection used by
                        # LeakSanitizer. Keep address/UB checks; the reporter has
                        # no allocation and its lifetime is not the test's target.
                        env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0")
                        subprocess.run([str(work / "check")], check=True, env=env)


if __name__ == "__main__":
    unittest.main()
