#ifndef RE4DC_SERIAL_LOG_FIFO_H
#define RE4DC_SERIAL_LOG_FIFO_H

#include <stdint.h>

namespace re4dc_serial {
// Caller owns SCIF and excludes interrupts for the entire query/write/ack burst.
// TDFE thresholds differ between SH7750 variants: consult the actual FIFO count.
template<class Port> unsigned tx_space()
{
    if (!(Port::status() & 0x20)) return 0;
    const unsigned queued = (Port::count() >> 8) & 0x1f;
    return queued < 16 ? 16 - queued : 0;
}
template<class Port> void acknowledge_tx()
{
    Port::status_write(static_cast<uint16_t>(Port::status() & ~0x60u));
}
}  // namespace re4dc_serial
#endif
