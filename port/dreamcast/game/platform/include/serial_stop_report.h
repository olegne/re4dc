#ifndef RE4DC_SERIAL_STOP_REPORT_H
#define RE4DC_SERIAL_STOP_REPORT_H

// Included after MissingSnapshot inside crash_screen.cpp's anonymous namespace.
// The hooks stay on existing source lines so SERIAL_LOG=0 also preserves its
// crash-test __LINE__ literal. Off contributes no state, calls or strings.
#if RE4DC_SERIAL_LOG

bool g_serial_watchdog_reported;

void serial_stop_snapshot(const char* kind, const MissingSnapshot& s, unsigned long stage)
{
    // Keep each record below re4dc_log's 256-byte formatter. A complete report
    // is below 1.1 KiB even with six latch rows; no heap or direct UART writes.
    char reason[80];
    unsigned n = 0;
    for (; n < sizeof(reason) - 1 && s.reason[n]; ++n) {
        const unsigned char c = static_cast<unsigned char>(s.reason[n]);
        reason[n] = c < 32 || c == 127 ? ' ' : static_cast<char>(c);
    }
    reason[n] = 0;
    re4dc_log("[RE4STOP first kind=%s reason=%.79s stage=%08lx ui=%u]\n", kind, reason, stage, s.ui);
    if (!s.pvr_valid) {
        re4dc_log("[RE4STOP pvr valid=0]\n");
        return;
    }
    re4dc_log("[RE4STOP pvr valid=1 frames=%u vbl=%u pending=%d ta_ready=%d]\n",
              s.frames, s.vbl, s.pending, s.ta_ready);
    re4dc_log("[RE4STOP regs vtx=%08x/%08x/%08x opb=%08x/%08x/%08x isp=%08x opb_init=%08x]\n",
              s.vtx[0], s.vtx[1], s.vtx[2], s.opb[0], s.opb[1], s.opb[2], s.isp, s.opb_init);
    re4dc_log("[RE4STOP asic a=%08x b=%08x c=%08x]\n", s.asic[0], s.asic[1], s.asic[2]);
#if RE4DC_PVR_LATCH
    for (unsigned i = 0; i < sizeof(s.latch) / sizeof(s.latch[0]); ++i)
        if (s.latch[i][0]) re4dc_log("[RE4STOP latch row=%u] %.53s\n", i, s.latch[i]);
#endif
}

void serial_stop_watchdog()
{
    // A sleeping MISSING already exported its original snapshot. A plain hang
    // has none; export the watchdog's current state without publishing it as a
    // first failure or changing the on-screen report. No per-frame work.
    if (g_missing.valid || g_serial_watchdog_reported || g_shown) return;
    g_serial_watchdog_reported = true;
    MissingSnapshot s{};
    unsigned long stage;
    const int old = irq_disable();
    snprintf(s.reason, sizeof(s.reason), "%s", "no new frame for 30 s");
    stage = re4dc_stage;
    s.ui = re4dc_ui_frame();
    pvr_stats_t st{};
    s.pvr_valid = pvr_get_stats(&st) == 0;
    if (s.pvr_valid) {
        s.frames = st.frame_count;
        s.vbl = st.vbl_count;
        s.pending = pvr_present_pending ? pvr_present_pending() : -1;
        s.ta_ready = pvr_check_ready();
        s.vtx[0] = PVR_GET(PVR_TA_VERTBUF_START);
        s.vtx[1] = PVR_GET(PVR_TA_VERTBUF_POS);
        s.vtx[2] = PVR_GET(PVR_TA_VERTBUF_END);
        s.opb[0] = PVR_GET(PVR_TA_OPB_START);
        s.opb[1] = PVR_GET(PVR_TA_OPB_POS); // raw register, as in the first-failure screen
        s.opb[2] = PVR_GET(PVR_TA_OPB_END);
        s.isp = PVR_GET(PVR_ISP_VERTBUF_ADDR);
        s.opb_init = PVR_GET(PVR_TA_OPB_INIT);
        s.asic[0] = *(volatile uint32_t*) ASIC_ACK_A;
        s.asic[1] = *(volatile uint32_t*) ASIC_ACK_B;
        s.asic[2] = *(volatile uint32_t*) ASIC_ACK_C;
#if RE4DC_PVR_LATCH
        for (unsigned i = 0; i < sizeof(s.latch) / sizeof(s.latch[0]); ++i)
            if (!re4dc_pvr_latch_line || !re4dc_pvr_latch_line(i, s.latch[i], sizeof(s.latch[i])))
                s.latch[i][0] = 0;
#endif
    }
    irq_restore(old);
    serial_stop_snapshot("watchdog", s, stage);
}

#define RE4DC_SERIAL_STOP_CAPTURE_DECL bool serial_first = false; unsigned long serial_stage = 0;
#define RE4DC_SERIAL_STOP_CAPTURE_FIRST() do { serial_stage = re4dc_stage; serial_first = true; } while (0)
#define RE4DC_SERIAL_STOP_CAPTURE_EMIT() do { if (serial_first) serial_stop_snapshot("missing", g_missing, serial_stage); } while (0)
#define RE4DC_SERIAL_STOP_WATCHDOG_EMIT() serial_stop_watchdog()

#else
#define RE4DC_SERIAL_STOP_CAPTURE_DECL
#define RE4DC_SERIAL_STOP_CAPTURE_FIRST() ((void)0)
#define RE4DC_SERIAL_STOP_CAPTURE_EMIT() ((void)0)
#define RE4DC_SERIAL_STOP_WATCHDOG_EMIT() ((void)0)
#endif

#endif
