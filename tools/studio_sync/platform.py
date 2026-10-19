from __future__ import annotations

import shutil
import subprocess
import sys


class FolderDialogError(RuntimeError):
    pass


def _active_x11_window() -> str:
    """Obtém a janela que originou o clique para anexar o diálogo no Linux/X11."""
    if not shutil.which("xdotool"):
        return ""
    result = subprocess.run(
        ["xdotool", "getactivewindow"], capture_output=True, text=True, check=False
    )
    window_id = result.stdout.strip()
    return window_id if result.returncode == 0 and window_id.isdigit() else ""


def choose_folder() -> str:
    """Abre o seletor de diretório nativo disponível no sistema operacional."""
    if sys.platform == "win32":
        command = [
            "powershell",
            "-NoProfile",
            "-STA",
            "-Command",
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$owner=New-Object System.Windows.Forms.Form; "
            "$owner.TopMost=$true; $owner.ShowInTaskbar=$false; "
            "$owner.StartPosition='CenterScreen'; $owner.Opacity=0; $owner.Show(); $owner.Activate(); "
            "$d=New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$d.Description='Selecione o repositório dos scripts'; "
            "if($d.ShowDialog($owner) -eq 'OK'){$d.SelectedPath}; $owner.Close()",
        ]
    elif sys.platform == "darwin":
        command = [
            "osascript",
            "-e",
            'tell application "Finder" to activate',
            "-e",
            'tell application "Finder" to POSIX path of (choose folder with prompt "Selecione o repositório dos scripts")',
        ]
    elif shutil.which("zenity"):
        command = [
            "zenity",
            "--file-selection",
            "--directory",
            "--title=Selecione o repositório dos scripts",
            "--modal",
        ]
        active_window = _active_x11_window()
        if active_window:
            command.append(f"--attach={active_window}")
    elif shutil.which("kdialog"):
        command = ["kdialog", "--getexistingdirectory", ".", "--title", "Repositório dos scripts"]
        active_window = _active_x11_window()
        if active_window:
            command.extend(["--attach", active_window])
    else:
        raise FolderDialogError("Nenhum seletor de pasta compatível foi encontrado.")

    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode not in (0, 1):
        raise FolderDialogError(result.stderr.strip() or "Não foi possível abrir o seletor de pasta.")
    return result.stdout.strip().rstrip("\r\n")
