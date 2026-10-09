"""Host regression of the actual adapter with fake KOS and mapped SCIF registers.

This validates control flow, budgets and register access in the production file;
it is not evidence of UART timing, scheduler behaviour or physical delivery.
"""
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PLATFORM = Path(__file__).resolve().parents[1] / "game/platform"
HEADERS = {
    "kos.h": r'''
#pragma once
#include <stdint.h>
#include <stddef.h>
struct kthread_t { int dummy; };
struct kthread_attr_t {
    void* stack_ptr;
    size_t stack_size;
    int prio;
    const char* label;
    bool disable_tls;
};
uint64_t timer_us_gettime64();
int irq_disable();
void irq_restore(int);
void thd_sleep(unsigned);
kthread_t* thd_create_ex(const kthread_attr_t*, void* (*)(void*), void*);
''',
    "dc/fs_dcload.h": r'''
#pragma once
#define DCLOAD_TYPE_SER 0
#define DCLOAD_TYPE_NONE (-1)
extern int dcload_type;
''',
    "dc/scif.h": r'''
#pragma once
void scif_set_parameters(int, int);
void scif_init();
''',
    "re4dc_platform.h": r'''
#pragma once
extern "C" void re4dc_log(const char*, ...);
''',
}
FIXTURE = r'''
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <string>

#define RE4DC_SERIAL_LOG 1
#define RE4DC_SERIAL_LOG_BUILD_ID "host-adapter-test"
#include "@SOURCE@"

extern "C" {
volatile unsigned long re4dc_log_head = 0;
volatile unsigned long re4dc_stage = 0;
char re4dc_logbuf[65536] = {};
int re4dc_log_console = 0;
}
int dcload_type = DCLOAD_TYPE_NONE;

static uint64_t fake_time, fake_step;
static unsigned timer_calls, disable_calls, restore_calls, log_calls;
static unsigned scif_calls, parameter_calls, create_calls;
static int last_baud, last_mode, last_restore;
static bool create_fail, auto_drain;
static kthread_attr_t recorded_attr;
static kthread_t fake_thread;
static void* (*recorded_entry)(void*);

static volatile uint16_t& status_register()
{ return *reinterpret_cast<volatile uint16_t*>(0xffe80010); }
static volatile uint16_t& count_register()
{ return *reinterpret_cast<volatile uint16_t*>(0xffe8001c); }
static volatile uint8_t& byte_register()
{ return *reinterpret_cast<volatile uint8_t*>(0xffe8000c); }
static void ready(unsigned queued = 0)
{
    status_register() = 0x60;
    count_register() = static_cast<uint16_t>(queued << 8);
}

uint64_t timer_us_gettime64()
{
    ++timer_calls;
    if (auto_drain) ready();
    const uint64_t result = fake_time;
    fake_time += fake_step;
    return result;
}
int irq_disable() { ++disable_calls; return 0x5678; }
void irq_restore(int token) { ++restore_calls; last_restore = token; }
void thd_sleep(unsigned) {}
kthread_t* thd_create_ex(const kthread_attr_t* attr, void* (*entry)(void*), void*)
{
    ++create_calls;
    recorded_attr = *attr;
    recorded_entry = entry;
    return create_fail ? nullptr : &fake_thread;
}
void scif_set_parameters(int baud, int mode)
{ ++parameter_calls; last_baud = baud; last_mode = mode; }
void scif_init() { ++scif_calls; }
extern "C" void re4dc_log(const char*, ...) { ++log_calls; }

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "line %d: %s\n", __LINE__, #x); return 1; \
} } while (0)

static void produce(unsigned count)
{
    for (unsigned i = 0; i < count; ++i) {
        const uint32_t head = static_cast<uint32_t>(re4dc_log_head);
        re4dc_logbuf[head & 65535] = static_cast<char>('A' + head % 26);
        re4dc_log_head = static_cast<uint32_t>(head + 1);
    }
}

int main(int argc, char** argv)
{
    if (argc != 2) return 2;
#ifndef MAP_FIXED_NOREPLACE
    return 77;
#else
    void* const wanted = reinterpret_cast<void*>(0xffe80000);
    void* mapped = mmap(wanted, 4096, PROT_READ | PROT_WRITE,
                        MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0);
    if (mapped == MAP_FAILED) return 77;
    if (mapped != wanted) { munmap(mapped, 4096); return 77; }
#endif
    const std::string name(argv[1]);
    if (name == "dcload_owns_serial") {
        dcload_type = DCLOAD_TYPE_SER;
        re4dc_serial_log_init();
        CHECK(!g_ready && g_started && log_calls == 1);
        CHECK(scif_calls == 0 && parameter_calls == 0 && create_calls == 0);
    } else if (name == "ram_logger_required") {
        re4dc_log_console = 1;
        re4dc_serial_log_init();
        CHECK(!g_ready && log_calls == 1);
        CHECK(scif_calls == 0 && parameter_calls == 0 && create_calls == 0);
    } else if (name == "init_once") {
        re4dc_serial_log_init();
        re4dc_serial_log_init();
        CHECK(g_ready && g_started && !g_stopped && log_calls == 0);
        CHECK(scif_calls == 1 && parameter_calls == 1 && create_calls == 1);
        CHECK(last_baud == 115200 && last_mode == 0);
        CHECK(recorded_attr.stack_ptr == g_stack && recorded_attr.stack_size == 4096);
        CHECK(reinterpret_cast<uintptr_t>(recorded_attr.stack_ptr) % 32 == 0);
        CHECK(recorded_attr.prio == 8 && recorded_attr.disable_tls);
        CHECK(strcmp(recorded_attr.label, "re4serial") == 0 && recorded_entry == worker);
        CHECK(disable_calls == 1 && restore_calls == 1 && last_restore == 0x5678);
        CHECK(g_notice_size > 0 && g_notice_size <= sizeof(g_notice));
    } else if (name == "thread_failure") {
        create_fail = true;
        re4dc_serial_log_init();
        CHECK(!g_ready && g_started && log_calls == 1 && create_calls == 1);
        CHECK(disable_calls == 1 && restore_calls == 1);
        re4dc_serial_log_emergency();
        CHECK(timer_calls == 0 && !g_emergency);
    } else if (name == "full_fifo") {
        produce(8);
        ready(16);
        CHECK(pump(0, false) == 0);
        CHECK(g_cursor.next == 0 && g_cursor.sent == 0 && g_busy == 1);
    } else if (name == "no_tdfe") {
        produce(8);
        status_register() = 0x40;
        count_register() = 0;
        CHECK(pump(0, false) == 0);
        CHECK(g_cursor.next == 0 && g_cursor.sent == 0 && g_busy == 1);
    } else if (name == "bounded_raw_burst") {
        produce(40);
        ready(0);
        CHECK(pump(0, false) == 16);
        CHECK(g_cursor.sent == 16 && g_cursor.next == 16);
        CHECK(byte_register() == static_cast<uint8_t>(re4dc_logbuf[15]));
        CHECK(status_register() == 0);
        ready(8);
        status_register() = 0xffff;
        CHECK(pump(0, false) == 8);
        CHECK(g_cursor.sent == 24 && g_cursor.next == 24);
        CHECK(byte_register() == static_cast<uint8_t>(re4dc_logbuf[23]));
        CHECK(status_register() == 0xff9f);
        ready(15);
        CHECK(pump(0, false) == 1 && g_cursor.sent == 25);
    } else if (name == "continuous_overrun_keeps_raw_progress") {
        for (unsigned i = 0; i < 300; ++i) {
            produce(65537);
            ready();
            CHECK(pump(i, true) <= 16);
            CHECK(g_notice_pos <= g_notice_size && g_notice_size <= sizeof(g_notice));
            if (i >= 20) CHECK(g_cursor.sent > 0);
        }
        CHECK(g_cursor.sent >= 64 && g_cursor.lost > 0 && g_reported_lost > 0);
    } else if (name == "notice_bounds") {
        std::string long_text(2048, 'x');
        notice_start(long_text.c_str());
        CHECK(g_notice_size == sizeof(g_notice) && g_notice_pos == 0);
        hex(UINT32_MAX);
        text(long_text.c_str());
        CHECK(g_notice_size == sizeof(g_notice));
        g_cursor.next = g_cursor.sent = g_cursor.lost = UINT32_MAX;
        g_polls = g_busy = g_max_poll_us = UINT32_MAX;
        re4dc_stage = UINT32_MAX;
        stats_notice(UINT32_MAX, UINT32_MAX);
        CHECK(g_notice_size > 0 && g_notice_size <= sizeof(g_notice));
        loss_notice();
        CHECK(g_notice_size > 0 && g_notice_size <= sizeof(g_notice));
    } else if (name == "emergency_time_bound") {
        g_ready = true;
        produce(4096);
        fake_step = 50000;
        auto_drain = true;
        re4dc_serial_log_emergency();
        CHECK(g_stopped && g_emergency && timer_calls == 5 && g_polls == 3);
        CHECK(g_cursor.lost == 2048 && g_cursor.next < re4dc_log_head);
        const unsigned calls = timer_calls;
        re4dc_serial_log_emergency();
        CHECK(timer_calls == calls);
    } else if (name == "emergency_frozen_clock_bound") {
        g_ready = true;
        produce(4096);
        ready(16);
        re4dc_serial_log_emergency();
        CHECK(g_stopped && g_emergency && g_polls == kEmergencyPolls);
        CHECK(timer_calls == kEmergencyPolls + 1 && g_busy == kEmergencyPolls);
        CHECK(g_cursor.sent == 0 && g_cursor.next == 2048 && g_cursor.lost == 2048);
    } else if (name == "emergency_only_latest_tail") {
        g_ready = true;
        produce(70000);
        fake_step = 1;
        auto_drain = true;
        re4dc_serial_log_emergency();
        CHECK(g_stopped && g_emergency);
        CHECK(g_cursor.sent == 2048 && g_cursor.lost == 70000 - 2048);
        CHECK(g_cursor.next == re4dc_log_head && g_notice_pos == g_notice_size);
        CHECK(byte_register() == static_cast<uint8_t>(re4dc_logbuf[(70000 - 1) & 65535]));
        CHECK(g_polls < 256 && timer_calls < 258);
    } else {
        return 2;
    }
    return 0;
}
'''


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux mmap fixture required")
class SerialLogAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("a host C++ compiler is required")
        cls.tmp = tempfile.TemporaryDirectory(prefix="re4dc-serial-adapter-")
        cls.addClassCleanup(cls.tmp.cleanup)
        root = Path(cls.tmp.name)
        for name, content in HEADERS.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        source = root / "adapter.cpp"
        source.write_text(
            FIXTURE.replace("@SOURCE@", (PLATFORM / "serial_log.cpp").as_posix()),
            encoding="utf-8",
        )
        cls.executable = root / "adapter-test"
        result = subprocess.run(
            [compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-O2", "-I", str(root), "-I", str(PLATFORM / "include"),
             str(source), "-o", str(cls.executable)],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)

    def run_case(self, name):
        result = subprocess.run(
            [str(self.executable), name], capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 77:
            self.skipTest("cannot safely map the SH7750 register page on this host")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


def _case(name):
    def test(self):
        self.run_case(name)
    test.__name__ = "test_" + name
    return test


for _name in (
    "dcload_owns_serial", "ram_logger_required", "init_once", "thread_failure",
    "full_fifo", "no_tdfe", "bounded_raw_burst",
    "continuous_overrun_keeps_raw_progress", "notice_bounds",
    "emergency_time_bound", "emergency_frozen_clock_bound", "emergency_only_latest_tail",
):
    setattr(SerialLogAdapter, "test_" + _name, _case(_name))


if __name__ == "__main__":
    unittest.main()
