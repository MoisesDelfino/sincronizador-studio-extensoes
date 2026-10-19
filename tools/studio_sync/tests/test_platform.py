from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools.studio_sync.platform import choose_folder


class FolderDialogTests(unittest.TestCase):
    @patch("tools.studio_sync.platform.subprocess.run")
    @patch("tools.studio_sync.platform.sys.platform", "win32")
    def test_windows_uses_powershell(self, run: Mock) -> None:
        run.return_value = Mock(returncode=0, stdout="C:\\Scripts\r\n", stderr="")
        self.assertEqual("C:\\Scripts", choose_folder())
        self.assertEqual("powershell", run.call_args.args[0][0])

    @patch("tools.studio_sync.platform.subprocess.run")
    @patch("tools.studio_sync.platform.sys.platform", "darwin")
    def test_macos_uses_osascript(self, run: Mock) -> None:
        run.return_value = Mock(returncode=0, stdout="/Users/teste/Scripts/\n", stderr="")
        self.assertEqual("/Users/teste/Scripts/", choose_folder())
        self.assertEqual("osascript", run.call_args.args[0][0])

    @patch("tools.studio_sync.platform.subprocess.run")
    @patch("tools.studio_sync.platform.shutil.which", return_value="/usr/bin/zenity")
    @patch("tools.studio_sync.platform.sys.platform", "linux")
    def test_linux_uses_zenity(self, _which: Mock, run: Mock) -> None:
        run.return_value = Mock(returncode=0, stdout="/home/teste/scripts\n", stderr="")
        self.assertEqual("/home/teste/scripts", choose_folder())
        self.assertEqual("zenity", run.call_args.args[0][0])
        self.assertIn("--modal", run.call_args.args[0])

    @patch("tools.studio_sync.platform.subprocess.run")
    @patch("tools.studio_sync.platform.shutil.which")
    @patch("tools.studio_sync.platform.sys.platform", "linux")
    def test_linux_attaches_dialog_to_active_window(self, which: Mock, run: Mock) -> None:
        which.side_effect = lambda name: f"/usr/bin/{name}" if name in ("zenity", "xdotool") else None
        run.side_effect = [
            Mock(returncode=0, stdout="98765\n", stderr=""),
            Mock(returncode=0, stdout="/home/teste/scripts\n", stderr=""),
        ]
        self.assertEqual("/home/teste/scripts", choose_folder())
        self.assertIn("--attach=98765", run.call_args_list[1].args[0])


if __name__ == "__main__":
    unittest.main()
