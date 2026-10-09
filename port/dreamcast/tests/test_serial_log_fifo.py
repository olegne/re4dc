"""Exercise the production SCIF FIFO policy with a register-access fake."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


INCLUDE = Path(__file__).resolve().parents[1] / "game/platform/include"
FIXTURE = r'''
#include "serial_log_fifo.h"
#include <stdio.h>
#include <string>

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "line %d: %s\n", __LINE__, #x); return 1; \
} } while (0)

struct Port {
    static uint16_t flags;
    static uint16_t fifo;
    static uint16_t written;
    static unsigned status_reads;
    static unsigned count_reads;
    static unsigned writes;
    static uint16_t status() { ++status_reads; return flags; }
    static uint16_t count() { ++count_reads; return fifo; }
    static void status_write(uint16_t value) { ++writes; written = value; }
    // The acknowledgement must issue a 16-bit write, not an int/32-bit write.
    template<class T> static void status_write(T) = delete;
};
uint16_t Port::flags = 0x20;
uint16_t Port::fifo = 0;
uint16_t Port::written = 0;
unsigned Port::status_reads = 0;
unsigned Port::count_reads = 0;
unsigned Port::writes = 0;

int main(int argc, char** argv)
{
    if (argc != 2) return 2;
    const std::string name(argv[1]);
    if (name == "tdfe_off") {
        Port::flags = 0xffdf;
        CHECK(re4dc_serial::tx_space<Port>() == 0);
        CHECK(Port::status_reads == 1 && Port::count_reads == 0 && Port::writes == 0);
    } else if (name == "empty") {
        CHECK(re4dc_serial::tx_space<Port>() == 16);
    } else if (name == "half") {
        Port::fifo = 8u << 8;
        CHECK(re4dc_serial::tx_space<Port>() == 8);
    } else if (name == "almost_full") {
        Port::fifo = 15u << 8;
        CHECK(re4dc_serial::tx_space<Port>() == 1);
    } else if (name == "full") {
        Port::fifo = 16u << 8;
        CHECK(re4dc_serial::tx_space<Port>() == 0);
    } else if (name == "overfull") {
        Port::fifo = 17u << 8;
        CHECK(re4dc_serial::tx_space<Port>() == 0);
    } else if (name == "max_count") {
        Port::fifo = 31u << 8;
        CHECK(re4dc_serial::tx_space<Port>() == 0);
    } else if (name == "count_mask") {
        Port::fifo = 0xe8ff;
        CHECK(re4dc_serial::tx_space<Port>() == 8);
    } else if (name == "ack_preserves_other_bits") {
        Port::flags = 0xffff;
        re4dc_serial::acknowledge_tx<Port>();
        CHECK(Port::written == 0xff9f && Port::writes == 1);
        CHECK(Port::status_reads == 1 && Port::count_reads == 0);
    } else if (name == "ack_no_flags") {
        Port::flags = 0x8197;
        re4dc_serial::acknowledge_tx<Port>();
        CHECK(Port::written == 0x8197 && Port::writes == 1);
    } else if (name == "query_does_not_ack") {
        Port::flags = 0x60;
        CHECK(re4dc_serial::tx_space<Port>() == 16);
        CHECK(Port::status_reads == 1 && Port::count_reads == 1 && Port::writes == 0);
    } else {
        return 2;
    }
    return 0;
}
'''


class SerialLogFifo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("a host C++ compiler is required")
        cls.tmp = tempfile.TemporaryDirectory(prefix="re4dc-serial-fifo-")
        cls.addClassCleanup(cls.tmp.cleanup)
        source = Path(cls.tmp.name) / "fifo.cpp"
        source.write_text(FIXTURE, encoding="utf-8")
        cls.executable = Path(cls.tmp.name) / "fifo-test"
        subprocess.run(
            [compiler, "-std=c++11", "-Wall", "-Wextra", "-Werror", "-pedantic",
             "-O2", "-I", str(INCLUDE), str(source), "-o", str(cls.executable)],
            check=True, capture_output=True, text=True,
        )

    def run_case(self, name):
        result = subprocess.run(
            [str(self.executable), name], capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


def _case(name):
    def test(self):
        self.run_case(name)
    test.__name__ = "test_" + name
    return test


for _name in (
    "tdfe_off", "empty", "half", "almost_full", "full", "overfull", "max_count",
    "count_mask", "ack_preserves_other_bits", "ack_no_flags", "query_does_not_ack",
):
    setattr(SerialLogFifo, "test_" + _name, _case(_name))


if __name__ == "__main__":
    unittest.main()
