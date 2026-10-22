"""install.sh / uninstall.sh against a fake $HOME, without launchctl or building the helper.

Run: python3 -m unittest discover tests
"""

import os
import plistlib
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run(script, home, *args):
    env = dict(os.environ, HOME=str(home), WIFI_HEATMAP_NO_LAUNCHCTL="1", WIFI_HEATMAP_NO_HELPER="1",
               WIFI_HEATMAP_NO_APP="1", WIFI_HEATMAP_HOME=str(home / "wh"))
    return subprocess.run(["sh", str(REPO / script)] + list(args), env=env, capture_output=True, text=True)


class Install(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp())

    def test_scripts_parse(self):
        for script in ("install.sh", "uninstall.sh", "bin/wifi-heatmap", "tools/build-helper.sh",
                       "tools/screenshots.sh", "tools/make-app.sh"):
            self.assertEqual(subprocess.run(["sh", "-n", str(REPO / script)]).returncode, 0, script)

    def test_command_only(self):
        p = run("install.sh", self.home)
        self.assertEqual(p.returncode, 0, p.stderr)
        link = self.home / ".local/bin/wifi-heatmap"
        self.assertTrue(link.is_symlink())
        self.assertEqual(Path(os.readlink(str(link))), REPO / "bin/wifi-heatmap")
        self.assertFalse((self.home / "Library/LaunchAgents/com.wifiheatmap.serve.plist").exists())

    def test_agent(self):
        p = run("install.sh", self.home, "--agent")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        with open(str(self.home / "Library/LaunchAgents/com.wifiheatmap.serve.plist"), "rb") as f:
            plist = plistlib.load(f)
        self.assertEqual(plist["ProgramArguments"], [str(REPO / "bin/wifi-heatmap"), "serve", "--no-open"])
        self.assertNotIn("--lan", plist["ProgramArguments"])   # the agent never opens the dashboard to the LAN
        self.assertEqual(plist["EnvironmentVariables"]["WIFI_HEATMAP_HOME"], str(self.home / "wh"))
        self.assertTrue(plist["StandardOutPath"].endswith("logs/serve.log"))

    def test_agent_lan(self):
        p = run("install.sh", self.home, "--agent", "--lan")
        self.assertEqual(p.returncode, 0, p.stderr + p.stdout)
        with open(str(self.home / "Library/LaunchAgents/com.wifiheatmap.serve.plist"), "rb") as f:
            args = plistlib.load(f)["ProgramArguments"]
        self.assertEqual(args[1:], ["serve", "--no-open", "--lan"])
        self.assertIn("your phone", p.stdout)

    def test_bad_options(self):
        self.assertNotEqual(run("install.sh", self.home, "--bogus").returncode, 0)
        self.assertNotEqual(run("install.sh", self.home, "--lan").returncode, 0)   # --lan needs --agent

    def test_uninstall_keeps_data_unless_purge(self):
        run("install.sh", self.home, "--agent")
        (self.home / "wh" / "samples.jsonl").write_text("{}\n")
        p = run("uninstall.sh", self.home)
        self.assertEqual(p.returncode, 0)
        self.assertFalse((self.home / ".local/bin/wifi-heatmap").exists())
        self.assertFalse((self.home / "Library/LaunchAgents/com.wifiheatmap.serve.plist").exists())
        self.assertTrue((self.home / "wh" / "samples.jsonl").exists())
        run("uninstall.sh", self.home, "--purge")
        self.assertFalse((self.home / "wh").exists())


class Icon(unittest.TestCase):
    def test_icon_draws_from_the_dashboard_art(self):
        out = Path(tempfile.mkdtemp()) / "icon.png"
        p = subprocess.run(["/usr/bin/python3", str(REPO / "tools/icon.py"), str(out), "64"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        data = out.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(data[16:24], (64).to_bytes(4, "big") * 2)   # IHDR width, height


if __name__ == "__main__":
    unittest.main()
