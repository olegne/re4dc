"""Run the real config generator against disposable, genuine Git repositories."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


GENERATOR = Path(__file__).resolve().parents[1] / "game/tools/gen_serial_log_config.py"


class SerialLogConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="re4dc-serial-config-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "source"
        self.script = self.root / "port/dreamcast/game/tools/gen_serial_log_config.py"
        self.script.parent.mkdir(parents=True)
        shutil.copyfile(GENERATOR, self.script)
        self.output = Path(self.tmp.name) / "build/include/serial_log_config.h"
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_")}
        self.env["GIT_CONFIG_NOSYSTEM"] = "1"
        self.env["GIT_CONFIG_GLOBAL"] = os.devnull
        # A test fixture outside a repository must not discover a parent worktree.
        self.env["GIT_CEILING_DIRECTORIES"] = self.tmp.name

    def git(self, *args):
        if not shutil.which("git"):
            self.skipTest("git is required")
        return subprocess.check_output(
            ["git", "-C", str(self.root), *args], env=self.env,
            text=True, stderr=subprocess.PIPE,
        ).strip()

    def init_commit(self):
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Serial test", "-c", "user.email=serial@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture")
        return self.git("rev-parse", "--short=12", "HEAD")

    def generate(self, enabled, check=True):
        return subprocess.run(
            [sys.executable, str(self.script), "--enabled", enabled,
             "--output", str(self.output)], env=self.env,
            check=check, text=True, capture_output=True, timeout=10,
        )

    def assert_config(self, enabled, build):
        self.assertEqual(
            self.output.read_text(),
            f'#define RE4DC_SERIAL_LOG {enabled}\n'
            f'#define RE4DC_SERIAL_LOG_BUILD_ID "{build}"\n',
        )
        self.assertFalse(self.output.with_name(self.output.name + ".tmp").exists())

    def test_enabled_clean_real_git_identity(self):
        revision = self.init_commit()
        self.generate("1")
        self.assert_config(1, revision)

    def test_enabled_dirty_real_git_identity(self):
        revision = self.init_commit()
        (self.root / "changed.txt").write_text("diagnostic edit\n")
        self.generate("1")
        self.assert_config(1, revision + "-dirty")

    def test_enabled_without_git_is_unknown(self):
        self.generate("1")
        self.assert_config(1, "unknown")

    def test_enabled_repository_without_head_is_unknown(self):
        self.git("init", "-q")
        self.generate("1")
        self.assert_config(1, "unknown")

    def test_disabled_does_not_need_git(self):
        self.env["PATH"] = ""
        self.generate("0")
        self.assert_config(0, "disabled")

    def test_unchanged_content_preserves_mtime(self):
        for enabled in ("0", "1"):
            with self.subTest(enabled=enabled):
                self.generate(enabled)
                old_time = 1_600_000_000_123_456_789
                os.utime(self.output, ns=(old_time, old_time))
                observed = self.output.stat().st_mtime_ns
                self.generate(enabled)
                self.assertEqual(self.output.stat().st_mtime_ns, observed)

    def test_toggling_rewrites_stale_switch(self):
        revision = self.init_commit()
        self.generate("1")
        self.assert_config(1, revision)
        self.generate("0")
        self.assert_config(0, "disabled")
        self.generate("1")
        self.assert_config(1, revision)

    def test_invalid_choices_do_not_create_or_overwrite_output(self):
        for invalid in ("2", "-1", "true", '1\n#define OTHER 1'):
            with self.subTest(invalid=invalid):
                result = self.generate(invalid, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid choice", result.stderr)
                self.assertFalse(self.output.exists())
        self.generate("0")
        before = self.output.read_bytes()
        result = self.generate("2", check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
