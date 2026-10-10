# Diagnostic UART export. Off by default; no source gameplay or play-recipe change.
SERIAL_LOG ?= 0
ifeq ($(filter $(SERIAL_LOG),0 1),)
$(error SERIAL_LOG must be 0 or 1)
endif
ifneq ($(SERIAL_LOG),1)
PLATFORM_OBJS := $(filter-out $(OBJDIR)/platform/serial_log.o,$(PLATFORM_OBJS))
endif
.PHONY: serial-log-force
$(OBJDIR)/serial-log-config.h: serial-log-force tools/gen_serial_log_config.py
	@mkdir -p $(dir $@)
	@python3 tools/gen_serial_log_config.py --enabled $(SERIAL_LOG) --output $@
SERIAL_LOG_OBJS = $(addprefix $(OBJDIR)/platform/,serial_log.o fault.o os.o mem.o crash_screen.o)
$(SERIAL_LOG_OBJS): $(OBJDIR)/serial-log-config.h platform/include/serial_log.h
$(SERIAL_LOG_OBJS): PLATFORM_CPPFLAGS += -include $(OBJDIR)/serial-log-config.h
$(OBJDIR)/platform/crash_screen.o: platform/include/serial_stop_report.h
