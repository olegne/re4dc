// Opt-in, single-owner export of the existing RAM ring. No serial TX function
// from KOS is used in the pump: scif_write[_buffer]/flush can busy-wait.
#include "serial_log.h"
#if RE4DC_SERIAL_LOG
#include <kos.h>
#include <dc/fs_dcload.h>
#include <dc/scif.h>
#include "re4dc_platform.h"
#include "serial_log_fifo.h"
#include "serial_log_ring.h"

#ifndef RE4DC_SERIAL_LOG_BUILD_ID
#define RE4DC_SERIAL_LOG_BUILD_ID "unknown"
#endif

extern "C" {
extern volatile unsigned long re4dc_log_head;
extern volatile unsigned long re4dc_stage;
extern char re4dc_logbuf[];
extern int re4dc_log_console;
}

namespace {
constexpr uint32_t kRingBytes = 0x10000;
constexpr uint32_t kEmergencyBytes = 2048;
constexpr uint64_t kEmergencyUs = 200000;
constexpr unsigned kEmergencyPolls = 1048576;

// Register widths and addresses from SH7750 SCIF, matching pinned KOS scif.c.
struct Scif {
    static uint16_t status() { return *reinterpret_cast<volatile uint16_t*>(0xffe80010); }
    static uint16_t count() { return *reinterpret_cast<volatile uint16_t*>(0xffe8001c); }
    static void byte(char c) { *reinterpret_cast<volatile uint8_t*>(0xffe8000c) = static_cast<uint8_t>(c); }
    static void status_write(uint16_t s) { *reinterpret_cast<volatile uint16_t*>(0xffe80010) = s; }
};

re4dc_serial::Cursor g_cursor;
char g_notice[256];
unsigned g_notice_size, g_notice_pos, g_raw_turn;
uint32_t g_reported_lost, g_polls, g_busy, g_max_poll_us, g_report_ms;
bool g_ready, g_started, g_stopped, g_emergency, g_line_start = true;
// Explicit stack: no implicit default-stack allocation. The KOS thread record
// still allocates; image/arena growth needs the normal H2/s30 memory gate.
uint8_t g_stack[4096] __attribute__((aligned(32)));

// Fixed bounded formatting, no stdio, heap, dbgio or ring writes in the pump.
void text(const char* s)
{
    for (; *s && g_notice_size < sizeof(g_notice); ++s) g_notice[g_notice_size++] = *s;
}
void hex(uint32_t value)
{
    static const char digits[] = "0123456789abcdef";
    text("0x");
    for (int shift = 28; shift >= 0 && g_notice_size < sizeof(g_notice); shift -= 4)
        g_notice[g_notice_size++] = digits[(value >> shift) & 15];
}
void notice_start(const char* kind)
{
    g_notice_size = g_notice_pos = 0;
    text("\n[RE4SER ");
    text(kind);
}
void loss_notice()
{
    notice_start("loss observed_bytes="); hex(g_cursor.lost);
    text(" sampled_next="); hex(g_cursor.next); text("]\n");
    g_reported_lost = g_cursor.lost;
}
void stats_notice(uint32_t head, uint32_t now_ms)
{
    notice_start("stats ms="); hex(now_ms);
    text(" head="); hex(head); text(" sent="); hex(g_cursor.sent);
    text(" backlog="); hex(head - g_cursor.next); text(" lost="); hex(g_cursor.lost);
    text(" polls="); hex(g_polls); text(" busy="); hex(g_busy);
    text(" max_poll_us="); hex(g_max_poll_us); text(" stage="); hex(static_cast<uint32_t>(re4dc_stage));
    text("]\n");
    g_report_ms = now_ms;
}

// Caller holds IRQ exclusion. One pass writes at most the 16 currently free
// FIFO slots and never waits for the UART or a receiver. Counter/ring reads and
// the byte copy happen together, so a preempted producer cannot overwrite data
// between the availability check and the burst. SERIAL_LOG also selects the
// existing atomic producer path; otherwise nested head++ could move head back.
unsigned pump(uint32_t now_ms, bool reports)
{
    ++g_polls;
    const uint32_t head = static_cast<uint32_t>(re4dc_log_head);
    re4dc_serial::reconcile(g_cursor, head, kRingBytes);
    if (g_notice_pos == g_notice_size && !g_raw_turn) {
        if (g_reported_lost != g_cursor.lost) loss_notice();
        else if (reports && g_line_start && static_cast<uint32_t>(now_ms - g_report_ms) >= 1000)
            stats_notice(head, now_ms);
    }
    unsigned slots = re4dc_serial::tx_space<Scif>();
    if (!slots) { ++g_busy; return 0; }
    unsigned wrote = 0;
    const bool had_notice = g_notice_pos < g_notice_size;
    while (slots && g_notice_pos < g_notice_size) {
        Scif::byte(g_notice[g_notice_pos++]);
        --slots; ++wrote;
    }
    // Guarantee raw progress under sustained overrun. A loss notice is a sampled
    // cumulative counter, not a promise that subsequent bytes are gap-free.
    if (had_notice && g_notice_pos == g_notice_size) g_raw_turn = 64;
    if (slots && g_notice_pos == g_notice_size) {
        const unsigned budget = g_raw_turn && g_raw_turn < slots ? g_raw_turn : slots;
        const unsigned raw = re4dc_serial::drain(re4dc_logbuf, kRingBytes, head, g_cursor, budget, [](char c) {
                Scif::byte(c);
                g_line_start = c == '\n';
                return true;
        });
        wrote += raw;
        if (g_raw_turn) g_raw_turn -= raw;
        if (g_cursor.next == head) g_raw_turn = 0;
    }
    if (wrote) re4dc_serial::acknowledge_tx<Scif>();
    return wrote;
}

void* worker(void*)
{
    for (;;) {
        const uint64_t begin = timer_us_gettime64();
        const int irq = irq_disable();
        if (g_stopped) { irq_restore(irq); return nullptr; }
        pump(static_cast<uint32_t>(begin / 1000), true);
        irq_restore(irq);
        const uint64_t elapsed = timer_us_gettime64() - begin;
        // Includes any scheduling delay, not a CPU-cycle measurement.
        if (elapsed <= UINT32_MAX && elapsed > g_max_poll_us) g_max_poll_us = static_cast<uint32_t>(elapsed);
        thd_sleep(1);  // Requested delay; actual polling cadence depends on KOS scheduling.
    }
}
}  // namespace

extern "C" void re4dc_serial_log_init(void)
{
    if (g_started) return;
    g_started = true;
    // Serial dcload owns the protocol. Never inject text or reconfigure it.
    // Also require fault_init to have successfully selected the RAM handler.
    if (dcload_type == DCLOAD_TYPE_SER || re4dc_log_console) {
        re4dc_log("RE4SER disabled: serial dcload active or RAM logger unavailable\n");
        return;
    }
    // Initialization only. Normal/fatal pumps never call KOS blocking TX APIs.
    scif_set_parameters(115200, 0);
    scif_init();
    notice_start("begin v=1 build=" RE4DC_SERIAL_LOG_BUILD_ID);
    text(" baud=115200 mode=rx-capture max_burst=16 sleep_ms=1]\n");
    kthread_attr_t attr = {};
    attr.stack_ptr = g_stack;
    attr.stack_size = sizeof(g_stack);
    attr.prio = 8;  // Above game tasks; still needs IRQs and scheduler progress.
    attr.label = "re4serial";
    attr.disable_tls = true;
    // Publish complete initialization before the newly created task can run.
    const int irq = irq_disable();
    g_ready = thd_create_ex(&attr, worker, nullptr) != nullptr;
    irq_restore(irq);
    if (!g_ready) re4dc_log("RE4SER disabled: cannot create capture task\n");
}

extern "C" void re4dc_serial_log_emergency(void)
{
    // Fault/HALT/OSPanic only, IRQs already disabled. Reentry cannot deadlock.
    if (!g_ready || g_emergency) return;
    g_emergency = g_stopped = true;
    const uint32_t head = static_cast<uint32_t>(re4dc_log_head);
    re4dc_serial::retain_tail(g_cursor, head, kRingBytes, kEmergencyBytes);
    notice_start("emergency best_effort max_us=200000 max_tail=2048 lost=");
    hex(g_cursor.lost); text(" next="); hex(g_cursor.next); text("]\n");
    g_reported_lost = g_cursor.lost;
    const uint64_t start = timer_us_gettime64();
    for (unsigned attempt = 0; attempt < kEmergencyPolls; ++attempt) {
        // An IRQ-off timer rollover may make elapsed jump: early termination
        // is acceptable; never extend the deadline or wait for receiver ACK.
        if (timer_us_gettime64() - start >= kEmergencyUs) break;
        pump(0, false);
        if (g_cursor.next == head && g_notice_pos == g_notice_size) break;
    }
    // Data remaining in the FIFO may still shift out. No flush and no promise
    // of complete delivery. The original crash screen/terminal halt stays intact.
}
#endif
