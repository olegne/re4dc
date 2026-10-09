"""Compile the production C++ ring cursor; no Dreamcast or serial port required."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


INCLUDE = Path(__file__).resolve().parents[1] / "game/platform/include"
FIXTURE = r'''
#include "serial_log_ring.h"
#include <stdio.h>
#include <string>

using re4dc_serial::Cursor;
using re4dc_serial::drain;
using re4dc_serial::reconcile;
using re4dc_serial::retain_tail;

#define CHECK(x) do { if (!(x)) { \
    fprintf(stderr, "line %d: %s\n", __LINE__, #x); return 1; \
} } while (0)

static void produce(char* ring, uint32_t capacity, uint32_t& head,
                    const std::string& text)
{
    for (char byte : text) {
        ring[head % capacity] = byte;
        ++head;
    }
}

int main(int argc, char** argv)
{
    if (argc != 2) return 2;
    const std::string name(argv[1]);
    char ring[8] = {};
    uint32_t head = 0;
    Cursor cursor;
    std::string output;
    unsigned calls = 0;
    auto accept = [&](char byte) { ++calls; output += byte; return true; };

    if (name == "empty") {
        CHECK(drain(ring, 8, head, cursor, 32, accept) == 0);
        CHECK(calls == 0 && cursor.next == 0 && cursor.sent == 0 && cursor.lost == 0);
    } else if (name == "budget") {
        produce(ring, 8, head, "abcdef");
        CHECK(drain(ring, 8, head, cursor, 0, accept) == 0);
        CHECK(calls == 0 && cursor.next == 0);
        CHECK(drain(ring, 8, head, cursor, 2, accept) == 2);
        CHECK(output == "ab" && cursor.next == 2 && cursor.sent == 2);
        CHECK(drain(ring, 8, head, cursor, 99, accept) == 4);
        CHECK(output == "abcdef" && cursor.sent == 6 && cursor.lost == 0);
    } else if (name == "physical_wrap") {
        head = cursor.next = 6;
        produce(ring, 8, head, "abcde");
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 5);
        CHECK(output == "abcde" && cursor.next == 11 && cursor.lost == 0);
    } else if (name == "counter_wrap") {
        head = cursor.next = UINT32_MAX - 2;
        cursor.sent = UINT32_MAX - 1;
        produce(ring, 8, head, "abcdef");
        CHECK(head == 3 && reconcile(cursor, head, 8) == 6);
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 6);
        CHECK(output == "abcdef" && cursor.next == 3 && cursor.sent == 4);
        CHECK(cursor.lost == 0);
    } else if (name == "overrun_one") {
        produce(ring, 8, head, "abcdefghi");
        CHECK(reconcile(cursor, head, 8) == 8);
        CHECK(cursor.next == 1 && cursor.lost == 1);
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 8);
        CHECK(output == "bcdefghi" && cursor.lost == 1);
    } else if (name == "overrun_many") {
        produce(ring, 8, head, "abcdefghijklmnopqrstuvwxyz");
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 8);
        CHECK(output == "stuvwxyz" && cursor.lost == 18 && cursor.next == 26);
    } else if (name == "overrun_counter_wrap") {
        head = cursor.next = UINT32_MAX - 3;
        produce(ring, 8, head, "abcdefghijkl");
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 8);
        CHECK(output == "efghijkl" && cursor.lost == 4 && cursor.next == head);
    } else if (name == "fifo_full") {
        produce(ring, 8, head, "ab");
        auto reject = [&](char byte) { ++calls; (void)byte; return false; };
        CHECK(drain(ring, 8, head, cursor, 8, reject) == 0);
        CHECK(calls == 1 && cursor.next == 0 && cursor.sent == 0 && cursor.lost == 0);
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 2);
        CHECK(output == "ab");
    } else if (name == "partial_accept") {
        produce(ring, 8, head, "abcdef");
        auto limited = [&](char byte) {
            ++calls;
            if (calls > 3) return false;
            output += byte;
            return true;
        };
        CHECK(drain(ring, 8, head, cursor, 8, limited) == 3);
        CHECK(output == "abc" && calls == 4 && cursor.next == 3 && cursor.sent == 3);
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 3);
        CHECK(output == "abcdef" && cursor.sent == 6);
    } else if (name == "no_resend") {
        produce(ring, 8, head, "abcd");
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 4);
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 0);
        CHECK(calls == 4 && output == "abcd");
        produce(ring, 8, head, "ef");
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 2);
        CHECK(output == "abcdef" && cursor.sent == 6);
    } else if (name == "tail") {
        produce(ring, 8, head, "abcdefghijkl");
        retain_tail(cursor, head, 8, 3);
        CHECK(cursor.next == 9 && cursor.lost == 9 && cursor.sent == 0);
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 3);
        CHECK(output == "jkl" && cursor.lost == 9);
    } else if (name == "tail_large") {
        produce(ring, 8, head, "abcdefghijkl");
        retain_tail(cursor, head, 8, 99);
        CHECK(cursor.next == 4 && cursor.lost == 4);
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 8);
        CHECK(output == "efghijkl");
    } else if (name == "discard_all") {
        produce(ring, 8, head, "abcdef");
        retain_tail(cursor, head, 8, 0);
        CHECK(cursor.next == head && cursor.lost == 6 && cursor.sent == 0);
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 0 && calls == 0);
        produce(ring, 8, head, "gh");
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 2);
        CHECK(output == "gh");
    } else if (name == "saturate_lost") {
        cursor.lost = UINT32_MAX - 2;
        produce(ring, 8, head, "abcdefghijkl");
        CHECK(reconcile(cursor, head, 8) == 8 && cursor.lost == UINT32_MAX);
        retain_tail(cursor, head, 8, 0);
        CHECK(cursor.lost == UINT32_MAX && cursor.next == head);
        cursor.lost = UINT32_MAX - 2;
        produce(ring, 8, head, "abc");
        retain_tail(cursor, head, 8, 0);
        CHECK(cursor.lost == UINT32_MAX);
    } else if (name == "producer_between_polls") {
        produce(ring, 8, head, "abcdef");
        CHECK(drain(ring, 8, head, cursor, 2, accept) == 2);
        produce(ring, 8, head, "ghijklmnop");
        CHECK(drain(ring, 8, head, cursor, 8, accept) == 8);
        CHECK(output == "abijklmnop" && cursor.lost == 6 && cursor.sent == 10);
    } else if (name == "production_capacity") {
        char actual[65536] = {};
        head = cursor.next = UINT32_MAX - 2;
        produce(actual, sizeof(actual), head, "abcdefgh");
        CHECK(drain(actual, sizeof(actual), head, cursor, 256, accept) == 8);
        CHECK(output == "abcdefgh" && cursor.next == head && cursor.lost == 0);
    } else {
        return 2;
    }
    return 0;
}
'''


class SerialLogRing(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = shutil.which("g++") or shutil.which("clang++")
        if not compiler:
            raise unittest.SkipTest("a host C++ compiler is required")
        cls.tmp = tempfile.TemporaryDirectory(prefix="re4dc-serial-ring-")
        cls.addClassCleanup(cls.tmp.cleanup)
        source = Path(cls.tmp.name) / "ring.cpp"
        source.write_text(FIXTURE, encoding="utf-8")
        cls.executable = Path(cls.tmp.name) / "ring-test"
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
    "empty", "budget", "physical_wrap", "counter_wrap", "overrun_one",
    "overrun_many", "overrun_counter_wrap", "fifo_full", "partial_accept",
    "no_resend", "tail", "tail_large", "discard_all", "saturate_lost",
    "producer_between_polls", "production_capacity",
):
    setattr(SerialLogRing, "test_" + _name, _case(_name))


if __name__ == "__main__":
    unittest.main()
