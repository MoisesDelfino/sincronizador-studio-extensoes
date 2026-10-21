from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import ChangeKind, SyncChange


def default_backup_root() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif os.sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "StudioSync" / "backups"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=".manifest-", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _restore_file(source: Path, target: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


class BackupError(RuntimeError):
    pass


class BackupStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_backup_root()).expanduser()

    def prepare(self, repository: Path, changes: list[SyncChange]) -> tuple[str, dict[str, Any]]:
        repository = repository.resolve()
        backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        directory = self.root / backup_id
        files = directory / "files"
        files.mkdir(parents=True, exist_ok=False)
        entries: list[dict[str, Any]] = []
        for index, change in enumerate(changes):
            if change.path is None or change.artifact is None:
                continue
            target = change.path.resolve()
            try:
                relative = target.relative_to(repository)
            except ValueError as exc:
                raise BackupError(f"Arquivo fora do repositório: {target}") from exc
            source = change.artifact.source_code.encode("utf-8")
            entry: dict[str, Any] = {
                "path": relative.as_posix(),
                "action": change.status.value,
                "after_sha256": _digest(source),
                "backup": "",
            }
            if change.status is ChangeKind.UPDATE:
                backup_name = f"{index:06d}.bak"
                shutil.copy2(target, files / backup_name)
                entry["backup"] = backup_name
            entries.append(entry)
        manifest: dict[str, Any] = {
            "id": backup_id,
            "repository": str(repository),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "prepared",
            "entries": entries,
        }
        _write_json_atomic(directory / "manifest.json", manifest)
        return backup_id, manifest

    def latest_applied(self, repository: Path) -> str:
        if not self.root.is_dir():
            return ""
        expected = repository.resolve()
        for directory in sorted(self.root.iterdir(), reverse=True):
            manifest_path = directory / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                same_repository = Path(str(manifest.get("repository", ""))).resolve() == expected
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if same_repository and manifest.get("status") == "applied":
                return str(manifest.get("id") or directory.name)
        return ""

    def mark_applied(self, backup_id: str, manifest: dict[str, Any]) -> None:
        manifest["status"] = "applied"
        _write_json_atomic(self.root / backup_id / "manifest.json", manifest)

    def abort(self, backup_id: str, manifest: dict[str, Any], repository: Path) -> None:
        """Reverte somente arquivos que chegaram ao conteúdo planejado antes de uma falha."""
        directory = self.root / backup_id
        for entry in reversed(manifest.get("entries", [])):
            target = (repository / str(entry["path"])).resolve()
            if not target.is_file() or _digest(target.read_bytes()) != entry.get("after_sha256"):
                continue
            if entry.get("action") == ChangeKind.CREATE.value:
                target.unlink()
            else:
                _restore_file(directory / "files" / str(entry["backup"]), target)
        manifest["status"] = "aborted"
        _write_json_atomic(directory / "manifest.json", manifest)

    def undo(self, backup_id: str, repository: Path) -> int:
        directory = self.root / backup_id
        manifest_path = directory / "manifest.json"
        if not manifest_path.is_file():
            raise BackupError("O backup da última sincronização não foi encontrado.")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BackupError("O manifesto do backup está corrompido ou inacessível.") from exc
        if manifest.get("status") != "applied":
            raise BackupError("A última sincronização já foi desfeita ou não foi concluída.")
        if Path(str(manifest.get("repository", ""))).resolve() != repository.resolve():
            raise BackupError("O backup pertence a outro repositório local.")

        resolved: list[tuple[dict[str, Any], Path]] = []
        conflicts: list[str] = []
        for entry in manifest.get("entries", []):
            target = (repository / str(entry["path"])).resolve()
            try:
                target.relative_to(repository.resolve())
            except ValueError as exc:
                raise BackupError("O backup contém um caminho inválido.") from exc
            if not target.is_file() or _digest(target.read_bytes()) != entry.get("after_sha256"):
                conflicts.append(str(entry["path"]))
            resolved.append((entry, target))
        if conflicts:
            names = ", ".join(conflicts[:5])
            suffix = "" if len(conflicts) <= 5 else f" e mais {len(conflicts) - 5}"
            raise BackupError(
                "Não foi possível desfazer porque estes arquivos mudaram depois da sincronização: "
                + names + suffix
            )

        restored = 0
        for entry, target in reversed(resolved):
            if entry.get("action") == ChangeKind.CREATE.value:
                target.unlink()
            else:
                source = directory / "files" / str(entry["backup"])
                _restore_file(source, target)
            restored += 1
        manifest["status"] = "undone"
        manifest["undone_at"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(manifest_path, manifest)
        return restored
