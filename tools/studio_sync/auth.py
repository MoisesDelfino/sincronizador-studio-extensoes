from __future__ import annotations

import threading
import time
import os
import base64
import re
import shutil
import sys
from pathlib import Path
from collections.abc import Callable
from urllib.parse import unquote

from .models import SessionCredentials


SCRIPTS_URL = "https://scripts.plataforma.betha.cloud/"


class AuthenticationError(RuntimeError):
    pass


def browser_profile_dir() -> Path:
    """Diretório privado e persistente usado somente pelo Chromium do aplicativo."""
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
        return root / "StudioSync" / "browser-profile"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "StudioSync" / "browser-profile"
    root = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return root / "studio-sync" / "browser-profile"


def selected_context_from_url(url: str) -> tuple[str, str]:
    """Retorna database/entity do contexto escolhido na navegação oficial."""
    matches = re.findall(r"(?:#/entidades/|/access/)([^/?#]+)", url, re.IGNORECASE)
    for encoded in matches:
        try:
            value = unquote(encoded)
            decoded = base64.b64decode(value + "=" * (-len(value) % 4)).decode()
        except Exception:
            continue
        database = re.search(r"(?:^|,)database:(\d+)(?:,|$)", decoded, re.IGNORECASE)
        entity = re.search(r"(?:^|,)entity:(\d+)(?:,|$)", decoded, re.IGNORECASE)
        if database and entity:
            return database.group(1), entity.group(1)
    return "", ""


def authenticate_interactively(
    timeout_seconds: int = 600,
    status: Callable[[str], None] | None = None,
    reset_session: bool = False,
) -> SessionCredentials:
    """Abre o login oficial e captura somente a sessão resultante.

    Usuário, senha e MFA são informados diretamente nas páginas da Betha.
    """
    if getattr(sys, "frozen", False):
        bundled_browsers = Path(getattr(sys, "_MEIPASS")) / "ms-playwright"
        if bundled_browsers.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled_browsers)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AuthenticationError(
            "Playwright não está instalado. Execute: pip install -r tools/studio_sync/requirements.txt"
        ) from exc

    report = status or (lambda _message: None)
    profile = browser_profile_dir()
    if reset_session and profile.exists():
        shutil.rmtree(profile)
    profile.mkdir(parents=True, exist_ok=True)
    try:
        profile.chmod(0o700)
    except OSError:
        pass
    captured: dict[str, str] = {}
    lock = threading.Lock()

    def capture_selected_context(url: str) -> None:
        database_id, entity_id = selected_context_from_url(url)
        if entity_id:
            captured["selected_database_id"] = database_id
            captured["selected_entity_id"] = entity_id

    def inspect_request(request: object) -> None:
        url = getattr(request, "url", "")
        if ".betha.cloud" not in url:
            return
        headers = getattr(request, "headers", {})
        authorization = headers.get("authorization", "")
        user_access = headers.get("user-access", "")
        with lock:
            capture_selected_context(url)
            if authorization.lower().startswith("bearer "):
                captured["access_token"] = authorization[7:].strip()
            if user_access:
                captured["user_access"] = user_access.strip()

    report("Abrindo o login oficial da Betha...")
    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                str(profile),
                headless=False,
            )
        except Exception as exc:
            raise AuthenticationError(
                "Não foi possível abrir o Chromium. Execute: playwright install chromium"
            ) from exc
        context.on("request", inspect_request)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(SCRIPTS_URL, wait_until="domcontentloaded", timeout=120_000)
        report("Conclua o login e o MFA na janela da Betha.")

        deadline = time.monotonic() + timeout_seconds
        try:
            while time.monotonic() < deadline:
                with lock:
                    capture_selected_context(page.url)
                    token = captured.get("access_token", "")
                    user_access = captured.get("user_access", "")
                    selected_entity_id = captured.get("selected_entity_id", "")
                    selected_database_id = captured.get("selected_database_id", "")
                if token and user_access and selected_entity_id:
                    report("Sessão autenticada.")
                    return SessionCredentials(
                        token,
                        user_access,
                        selected_entity_id=selected_entity_id,
                        selected_database_id=selected_database_id,
                    )
                if token and user_access:
                    report("Selecione a entidade que deseja utilizar na janela da Betha.")
                if page.is_closed():
                    raise AuthenticationError("A janela de login foi fechada antes da autenticação.")
                page.wait_for_timeout(500)
        finally:
            context.close()

    raise AuthenticationError("Tempo esgotado aguardando a autenticação.")

