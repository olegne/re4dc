#ifndef RE4DC_SERIAL_LOG_RING_H
#define RE4DC_SERIAL_LOG_RING_H

#include <stdint.h>

namespace re4dc_serial {

struct Cursor {
    uint32_t next = 0;
    uint32_t sent = 0;
    uint32_t lost = 0;
};

inline void add_lost(Cursor& cursor, uint32_t count)
{
    const uint32_t maximum = ~uint32_t(0);
    cursor.lost = count > maximum - cursor.lost
        ? maximum : cursor.lost + count;
}

// head and next are monotonic uint32_t byte counters (wrapping is expected).
// The caller supplies a positive capacity and a stable producer snapshot.
// A full 2^32 bytes without polling is indistinguishable from no production.
inline uint32_t reconcile(Cursor& cursor, uint32_t head, uint32_t capacity)
{
    const uint32_t available = head - cursor.next;
    if (available > capacity) {
        add_lost(cursor, available - capacity);
        cursor.next = head - capacity;
        return capacity;
    }
    return available;
}

inline void retain_tail(Cursor& cursor, uint32_t head, uint32_t capacity,
                        uint32_t keep)
{
    const uint32_t available = reconcile(cursor, head, capacity);
    if (available > keep) {
        add_lost(cursor, available - keep);
        cursor.next = head - keep;
    }
}

// write_byte returns true only when the byte was accepted. It must not block.
// Keep the producer/ring stable for this call; the Dreamcast caller masks IRQs.
// The production ring has power-of-two capacity, including across counter wrap.
template<class Writer>
inline uint32_t drain(const char* ring, uint32_t capacity, uint32_t head,
                      Cursor& cursor, uint32_t budget, Writer write_byte)
{
    const uint32_t available = reconcile(cursor, head, capacity);
    const uint32_t limit = available < budget ? available : budget;
    uint32_t accepted = 0;
    while (accepted < limit) {
        if (!write_byte(ring[cursor.next % capacity]))
            break;
        ++cursor.next;
        ++cursor.sent;
        ++accepted;
    }
    return accepted;
}

} // namespace re4dc_serial

#endif // RE4DC_SERIAL_LOG_RING_H
