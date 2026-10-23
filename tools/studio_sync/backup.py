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


def _tree_digest(path: Path) -> str:
    digest = hashlib.sha256()
    if not path.exists():
        digest.update(b"missing")
        return digest.hexdigest()
    for item in sorted(path.rglob("*"), key=lambda value: value.as_posix()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(relative)
        if item.is_symlink():
            digest.update(b"symlink")
            digest.update(os.readlink(item).encode("utf-8"))
        elif item.is_dir():
            digest.update(b"directory")
        else:
            digest.update(b"file")
            digest.update(item.read_bytes())
    return digest.hexdigest()


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

    def prepare(
        self,
        repository: Path,
        changes: list[SyncChange],
        directory_moves: list[tuple[Path, Path]] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        repository = repository.resolve()
        backup_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        directory = self.root / backup_id
        files = directory / "files"
        files.mkdir(parents=True, exist_ok=False)
        directory_backups = directory / "directories"
        directory_backups.mkdir()
        moves: list[dict[str, str]] = []
        affected_directories: set[Path] = set()
        for source, target in directory_moves or []:
            source = source.resolve()
            target = target.resolve()
            try:
                source_relative = source.relative_to(repository)
                target_relative = target.relative_to(repository)
            except ValueError as exc:
                raise BackupError("A movimentação contém uma pasta fora do repositório.") from exc
            moves.append({
                "source": source_relative.as_posix(),
                "target": target_relative.as_posix(),
            })
            affected_directories.update((source, target))

        snapshots: list[dict[str, str]] = []
        for index, path in enumerate(sorted(affected_directories, key=lambda item: item.as_posix())):
            if not path.exists():
                continue
            backup_name = f"{index:06d}"
            shutil.copytree(path, directory_backups / backup_name, symlinks=True)
            snapshots.append({
                "path": path.relative_to(repository).as_posix(),
                "backup": backup_name,
            })
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
                "directory_covered": any(
                    target == path or path in target.parents
                    for path in affected_directories
                ),
            }
            if change.status is ChangeKind.UPDATE and not entry["directory_covered"]:
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
            "directory_moves": moves,
            "directory_snapshots": snapshots,
            "directory_after": [],
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
        repository = Path(str(manifest["repository"])).resolve()
        paths = {
            str(move[key])
            for move in manifest.get("directory_moves", [])
            for key in ("source", "target")
        }
        manifest["directory_after"] = [
            {
                "path": relative,
                "exists": (repository / relative).exists(),
                "sha256": _tree_digest(repository / relative),
            }
            for relative in sorted(paths)
        ]
        manifest["status"] = "applied"
        _write_json_atomic(self.root / backup_id / "manifest.json", manifest)

    def _restore_directories(
        self,
        backup_id: str,
        manifest: dict[str, Any],
        repository: Path,
    ) -> int:
        affected = {
            str(move[key])
            for move in manifest.get("directory_moves", [])
            for key in ("source", "target")
        }
        for relative in affected:
            target = (repository / relative).resolve()
            try:
                target.relative_to(repository.resolve())
            except ValueError as exc:
                raise BackupError("O backup contém uma pasta inválida.") from exc
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
        directory = self.root / backup_id / "directories"
        for snapshot in manifest.get("directory_snapshots", []):
            target = repository / str(snapshot["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(directory / str(snapshot["backup"]), target, symlinks=True)
        return len(manifest.get("directory_moves", []))

    def abort(self, backup_id: str, manifest: dict[str, Any], repository: Path) -> None:
        """Reverte somente arquivos que chegaram ao conteúdo planejado antes de uma falha."""
        directory = self.root / backup_id
        for entry in reversed(manifest.get("entries", [])):
            if entry.get("directory_covered"):
                continue
            target = (repository / str(entry["path"])).resolve()
            if not target.is_file() or _digest(target.read_bytes()) != entry.get("after_sha256"):
                continue
            if entry.get("action") == ChangeKind.CREATE.value:
                target.unlink()
            else:
                _restore_file(directory / "files" / str(entry["backup"]), target)
        self._restore_directories(backup_id, manifest, repository)
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
            if (
                not entry.get("directory_covered")
                and (not target.is_file() or _digest(target.read_bytes()) != entry.get("after_sha256"))
            ):
                conflicts.append(str(entry["path"]))
            resolved.append((entry, target))
        for state in manifest.get("directory_after", []):
            target = (repository / str(state["path"])).resolve()
            exists = target.exists()
            if exists != bool(state.get("exists")) or _tree_digest(target) != state.get("sha256"):
                conflicts.append(str(state["path"]))
        if conflicts:
            names = ", ".join(conflicts[:5])
            suffix = "" if len(conflicts) <= 5 else f" e mais {len(conflicts) - 5}"
            raise BackupError(
                "Não foi possível desfazer porque estes arquivos mudaram depois da sincronização: "
                + names + suffix
            )

        restored = 0
        for entry, target in reversed(resolved):
            if entry.get("directory_covered"):
                restored += 1
                continue
            if entry.get("action") == ChangeKind.CREATE.value:
                target.unlink()
            else:
                source = directory / "files" / str(entry["backup"])
                _restore_file(source, target)
            restored += 1
        self._restore_directories(backup_id, manifest, repository)
        manifest["status"] = "undone"
        manifest["undone_at"] = datetime.now(timezone.utc).isoformat()
        _write_json_atomic(manifest_path, manifest)
        return restored
