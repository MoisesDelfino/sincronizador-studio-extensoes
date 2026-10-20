from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from collections import Counter
from dataclasses import replace
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .api import StudioApi
from .auth import authenticate_interactively
from .models import AccessOption, ArtifactKind, ChangeKind, SyncChange
from .sync import Synchronizer

STATIC = Path(__file__).with_name("static")


class AppState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.status = "Pronto para autenticar."
        self.busy = False
        self.user = ""
        self.api: StudioApi | None = None
        self.preferred_entity_id = ""
        self.accesses: list[AccessOption] = []
        self.summaries: list[tuple[ArtifactKind, dict[str, Any]]] = []
        self.changes: list[SyncChange | None] = []
        self.duplicate_names: set[str] = set()
        self.root: Path | None = None

    def update(self, status: str, busy: bool | None = None) -> None:
        with self.lock:
            self.status = status
            if busy is not None:
                self.busy = busy

    def public(self) -> dict[str, Any]:
        with self.lock:
            counts = {item.value: 0 for item in ChangeKind}
            for change in self.changes:
                if change is not None:
                    counts[change.status.value] += 1
            counts["PENDENTE"] = sum(change is None for change in self.changes)
            entities: dict[str, dict[str, Any]] = {}
            for index, access in enumerate(self.accesses):
                entity = entities.setdefault(
                    access.entity_id,
                    {"id": access.entity_id, "label": access.label, "systems": []},
                )
                system_key = access.system_id or access.system_name
                if not access.system_id and access.system_name == "Sistema não identificado":
                    continue
                duplicate = any(
                    item["key"] == system_key
                    or (
                        access.system_name == "Sistema não identificado"
                        and item["label"] == access.system_name
                    )
                    for item in entity["systems"]
                )
                if not duplicate:
                    entity["systems"].append(
                        {
                            "key": system_key,
                            "label": access.system_name,
                            "access": index,
                        }
                    )
            return {
                "status": self.status,
                "busy": self.busy,
                "authenticated": self.api is not None,
                "preferredEntity": self.preferred_entity_id,
                "user": self.user,
                "accesses": [
                    {"label": item.label, "system": item.system_name} for item in self.accesses
                ],
                "entities": sorted(entities.values(), key=lambda item: item["label"].casefold()),
                "counts": counts,
            }


STATE = AppState()


class Handler(BaseHTTPRequestHandler):
    server_version = "StudioSync/0.2"

    def log_message(self, _format: str, *args: object) -> None:
        return

    def send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        if self.path == "/api/state":
            self.send_json(STATE.public())
            return
        if self.path == "/api/changes":
            rows = []
            for index, (kind, summary) in enumerate(STATE.summaries):
                change = STATE.changes[index]
                title = str(summary.get("titulo") or summary.get("title") or summary.get("nome") or "desconhecido")
                rows.append({
                    "index": index,
                    "status": change.status.value if change else "PENDENTE",
                    "kind": change.artifact.kind.value if change and change.artifact else kind.value,
                    "title": change.artifact.title if change and change.artifact else title,
                    "path": str(change.path) if change and change.path else "",
                    "message": change.message if change else "O conteúdo será carregado ao abrir esta página.",
                    "actionable": bool(change and change.status in (ChangeKind.CREATE, ChangeKind.UPDATE)),
                    "loaded": change is not None,
                })
            self.send_json(rows)
            return
        relative = "index.html" if self.path in ("/", "") else self.path.lstrip("/")
        path = (STATIC / relative).resolve()
        if STATIC.resolve() not in path.parents and path != STATIC.resolve():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_POST(self) -> None:
        try:
            if self.path == "/api/authenticate":
                self.authenticate()
            elif self.path == "/api/folders":
                self.list_folders()
            elif self.path == "/api/systems":
                self.load_systems()
            elif self.path == "/api/analyze":
                self.analyze()
            elif self.path == "/api/page":
                self.load_page()
            elif self.path == "/api/apply":
                self.apply_changes()
            elif self.path == "/api/shutdown":
                self.send_json({"ok": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except Exception as exc:
            STATE.update(f"Erro: {exc}", False)
            self.send_json({"error": str(exc)}, 400)

    def authenticate(self) -> None:
        body = self.read_json()
        STATE.update("Abrindo sua sessão Betha...", True)
        credentials = authenticate_interactively(
            status=lambda value: STATE.update(value, True),
            reset_session=bool(body.get("resetSession")),
        )
        api = StudioApi(credentials)
        user = api.current_user()
        accesses = api.list_accesses()
        STATE.api = api
        STATE.summaries = []
        STATE.changes = []
        STATE.duplicate_names = set()
        STATE.preferred_entity_id = credentials.selected_entity_id
        STATE.accesses = accesses
        STATE.user = str(user.get("name") or user.get("nome") or user.get("email") or "Autenticado")
        entity_count = len({item.entity_id for item in accesses})
        STATE.update(f"Sessão conectada. {entity_count} entidade(s) disponível(is).", False)
        self.send_json(STATE.public())

    def list_folders(self) -> None:
        body = self.read_json()
        requested = str(body.get("path") or Path.home())
        current = Path(requested).expanduser().resolve()
        if not current.is_dir():
            raise ValueError("A pasta informada não existe ou não está acessível.")
        try:
            directories = sorted(
                (
                    {"name": child.name, "path": str(child.resolve())}
                    for child in current.iterdir()
                    if child.is_dir() and not child.name.startswith(".")
                ),
                key=lambda item: item["name"].casefold(),
            )
        except PermissionError as exc:
            raise ValueError("Sem permissão para visualizar esta pasta.") from exc
        parent = current.parent if current.parent != current else None
        self.send_json(
            {
                "path": str(current),
                "parent": str(parent) if parent else "",
                "directories": directories,
            }
        )

    def load_systems(self) -> None:
        body = self.read_json()
        entity_id = str(body.get("entity", ""))
        if STATE.api is None:
            raise ValueError("Faça a autenticação primeiro.")
        base = next((item for item in STATE.accesses if item.entity_id == entity_id), None)
        if base is None:
            raise ValueError("Selecione uma entidade válida.")
        STATE.update("Consultando os sistemas permitidos para a entidade...", True)
        systems = STATE.api.list_permitted_systems(base)
        with STATE.lock:
            existing = {
                item.system_id: item
                for item in STATE.accesses
                if item.entity_id == entity_id and item.system_id
            }
            systems = [
                replace(
                    existing.get(item.system_id, item),
                    system_name=item.system_name,
                )
                for item in systems
            ]
            STATE.accesses = [item for item in STATE.accesses if item.entity_id != entity_id]
            STATE.accesses.extend(systems)
        STATE.update(f"{len(systems)} sistema(s) disponível(is) para a entidade.", False)
        self.send_json(STATE.public())

    def analyze(self) -> None:
        body = self.read_json()
        if STATE.api is None:
            raise ValueError("Faça a autenticação primeiro.")
        access_index = int(body.get("access", -1))
        if not 0 <= access_index < len(STATE.accesses):
            raise ValueError("Selecione uma entidade.")
        folder = str(body.get("folder") or "").strip()
        if not folder:
            raise ValueError("Escolha a pasta local antes de analisar as diferenças.")
        root = Path(folder).expanduser()
        if not root.is_dir():
            raise ValueError("Selecione uma pasta local válida.")
        kinds = []
        if body.get("job"):
            kinds.append(ArtifactKind.JOB)
        if body.get("component"):
            kinds.append(ArtifactKind.COMPONENT)
        if body.get("critique"):
            kinds.append(ArtifactKind.CRITIQUE)
        if body.get("dynamicSource"):
            kinds.append(ArtifactKind.DYNAMIC_SOURCE)
        if not kinds:
            raise ValueError("Selecione ao menos um tipo de artefato.")
        STATE.update("Selecionando a entidade...", True)
        STATE.api.select_access(STATE.accesses[access_index])
        STATE.root = root
        STATE.api.cache_hits = 0
        STATE.api.cache_misses = 0
        summaries: list[tuple[ArtifactKind, dict[str, Any]]] = []
        synchronizer = Synchronizer(STATE.api, root)
        names: list[str] = []
        STATE.update("Carregando a lista de scripts...", True)
        for kind in kinds:
            kind_summaries = STATE.api.list_artifact_summaries(kind)
            summaries.extend((kind, summary) for summary in kind_summaries)
            for summary in kind_summaries:
                title = str(summary.get("titulo") or summary.get("title") or summary.get("nome") or "")
                try:
                    names.append(synchronizer.remote_filename_key(kind, title))
                except ValueError:
                    pass
        STATE.summaries = summaries
        STATE.changes = [None] * len(summaries)
        STATE.duplicate_names = {name for name, count in Counter(names).items() if count > 1}
        STATE.update(
            f"Lista carregada: {len(summaries)} item(ns). Abra uma página para analisar seu conteúdo.",
            False,
        )
        self.send_json(STATE.public())

    def load_page(self) -> None:
        if STATE.api is None or STATE.root is None or not STATE.summaries:
            raise ValueError("Execute a análise antes de carregar uma página.")
        body = self.read_json()
        requested = body.get("changes")
        if not isinstance(requested, list):
            raise ValueError("Informe os itens da página.")
        indexes = sorted({
            int(value) for value in requested
            if (isinstance(value, int) or (isinstance(value, str) and value.isdigit()))
            and 0 <= int(value) < len(STATE.summaries)
        })
        missing = [index for index in indexes if STATE.changes[index] is None]
        if missing:
            STATE.update(f"Carregando conteúdo de {len(missing)} item(ns) desta página...", True)
            selected = [STATE.summaries[index] for index in missing]
            analyzed = Synchronizer(STATE.api, STATE.root).analyze_summaries(
                selected,
                duplicate_names=STATE.duplicate_names,
                progress=lambda value: STATE.update(value, True),
            )
            for index, change in zip(missing, analyzed):
                STATE.changes[index] = change
        STATE.update(
            "Página analisada. "
            f"Cache: {STATE.api.cache_hits} reutilizado(s), {STATE.api.cache_misses} baixado(s).",
            False,
        )
        self.send_json({"loaded": len(missing)})

    def apply_changes(self) -> None:
        if STATE.api is None or STATE.root is None or not STATE.changes:
            raise ValueError("Execute a análise antes de sincronizar.")
        body = self.read_json()
        requested = body.get("changes")
        if not isinstance(requested, list):
            raise ValueError("Selecione ao menos um script para sincronizar.")
        selected_indexes = {
            int(value)
            for value in requested
            if isinstance(value, int) or (isinstance(value, str) and value.isdigit())
        }
        selected = [
            change
            for index, change in enumerate(STATE.changes)
            if index in selected_indexes and change is not None
            and change.status in (ChangeKind.CREATE, ChangeKind.UPDATE)
        ]
        if not selected:
            raise ValueError("Selecione ao menos um script novo ou atualizado.")
        details = [
            {
                "title": change.artifact.title if change.artifact else "Script sem título",
                "kind": change.artifact.kind.value if change.artifact else "",
                "action": change.status.value,
                "path": str(change.path) if change.path else "",
            }
            for change in selected
        ]
        applied_indexes = {
            index
            for index, change in enumerate(STATE.changes)
            if index in selected_indexes and change is not None
            and change.status in (ChangeKind.CREATE, ChangeKind.UPDATE)
        }
        STATE.update("Gravando arquivos com segurança...", True)
        count = Synchronizer(STATE.api, STATE.root).apply(selected)
        for index in applied_indexes:
            change = STATE.changes[index]
            if change is not None:
                STATE.changes[index] = replace(change, status=ChangeKind.UNCHANGED)
        STATE.update(f"Sincronização concluída: {count} arquivo(s) gravado(s).", False)
        self.send_json({
            "written": count,
            "created": sum(item["action"] == ChangeKind.CREATE.value for item in details),
            "updated": sum(item["action"] == ChangeKind.UPDATE.value for item in details),
            "items": details,
            "remaining": len(STATE.changes),
        })


def run() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_port}"
    threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()

