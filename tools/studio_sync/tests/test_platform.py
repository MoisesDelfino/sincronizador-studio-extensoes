from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import iniciar

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


class LinuxIntegrationTests(unittest.TestCase):
    def test_installs_icon_and_launcher_in_user_profile(self) -> None:
        with TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.png"
            source.write_bytes(b"custom-icon")
            home = Path(temporary) / "home"
            with patch.object(iniciar, "ICONE", source), patch.object(iniciar.Path, "home", return_value=home), patch.object(iniciar.sys, "platform", "linux"):
                iniciar.instalar_integracao_linux()
            installed = home / ".local/share/icons/hicolor/512x512/apps/studio-sync.png"
            self.assertEqual(installed.read_bytes(), b"custom-icon")
            launcher = home / ".local/share/applications/sincronizador-studio.desktop"
            self.assertIn("iniciar.py", launcher.read_text(encoding="utf-8"))
            self.assertNotIn("sincronizar_studio.py", launcher.read_text(encoding="utf-8"))


class RepositoryUpdateTests(unittest.TestCase):
    @patch.object(iniciar.shutil, "which", return_value="/usr/bin/git")
    @patch.object(iniciar.subprocess, "run")
    def test_updates_with_fast_forward_only_before_starting(self, run: Mock, _which: Mock) -> None:
        run.return_value = Mock(returncode=0, stdout="Already up to date.\n", stderr="")
        env = {"EXISTING": "value"}
        with patch.object(iniciar, "RAIZ", Path(".")):
            self.assertTrue(iniciar.atualizar_repositorio(env))
        self.assertEqual("current", env["STUDIO_SYNC_VERSION_STATUS"])
        self.assertEqual(["git", "pull", "--ff-only"], run.call_args.args[0])
        self.assertEqual("0", run.call_args.kwargs["env"]["GIT_TERMINAL_PROMPT"])
        self.assertEqual(30, run.call_args.kwargs["timeout"])

    @patch.object(iniciar.shutil, "which", return_value="/usr/bin/git")
    @patch.object(iniciar.subprocess, "run")
    def test_failed_update_does_not_block_local_start(self, run: Mock, _which: Mock) -> None:
        run.return_value = Mock(returncode=1, stdout="", stderr="local changes")
        env = {}
        with patch.object(iniciar, "RAIZ", Path(".")):
            self.assertFalse(iniciar.atualizar_repositorio(env))
        self.assertEqual("unavailable", env["STUDIO_SYNC_VERSION_STATUS"])

if __name__ == "__main__":
    unittest.main()
