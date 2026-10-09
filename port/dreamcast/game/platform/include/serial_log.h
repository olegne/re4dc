#ifndef RE4DC_SERIAL_LOG_H
#define RE4DC_SERIAL_LOG_H

#ifndef RE4DC_SERIAL_LOG
#define RE4DC_SERIAL_LOG 0
#endif

#if RE4DC_SERIAL_LOG
extern "C" void re4dc_serial_log_init(void);
// Only after the game has already chosen to halt, with interrupts disabled.
extern "C" void re4dc_serial_log_emergency(void);
#else
static inline void re4dc_serial_log_init(void) {}
static inline void re4dc_serial_log_emergency(void) {}
#endif

#endif
