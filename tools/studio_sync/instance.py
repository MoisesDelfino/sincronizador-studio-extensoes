from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .auth import browser_profile_dir


def runtime_file() -> Path:
    return browser_profile_dir().parent / "server.json"


def running_instance_url() -> str:
    path = runtime_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        port = int(data["port"])
        if not 1 <= port <= 65535:
            raise ValueError("Porta inválida")
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return ""

    url = f"http://127.0.0.1:{port}"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(f"{url}/api/state", timeout=0.75) as response:
                server = response.headers.get("Server", "")
                state = json.loads(response.read())
                if response.status == 200 and server.startswith("StudioSync/") and "authenticated" in state:
                    return url
        except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
            if attempt < 2:
                time.sleep(0.15)
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
    return ""


def register_running_instance(port: int) -> None:
    path = runtime_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps({"port": port}), encoding="utf-8")
        try:
            temporary.chmod(0o600)
        except OSError:
            pass
        temporary.replace(path)
    except OSError:
        pass


def clear_running_instance(port: int) -> None:
    path = runtime_file()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if int(data.get("port", 0)) == port:
            path.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
