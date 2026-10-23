from __future__ import annotations

import os
import re
import shutil
import tempfile
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path

from .api import StudioApi, StudioApiError
from .backup import BackupStore
from .models import ArtifactKind, ChangeKind, RemoteArtifact, SyncChange


INVALID_FILENAME_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL", *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
DIRECTORY_ALIASES = {
    ArtifactKind.COMPONENT: {"Components"},
}


class Synchronizer:
    def __init__(self, api: StudioApi, root: Path, backups: BackupStore | None = None) -> None:
        self.api = api
        self.root = root.expanduser().resolve()
        self.backups = backups or BackupStore()
        self.last_backup_id = ""

    def _target(self, artifact: RemoteArtifact) -> Path:
        title = artifact.title.strip()
        safe_title = INVALID_FILENAME_CHARACTERS.sub(" - ", title)
        safe_title = re.sub(r"\s+", " ", safe_title).strip(" .")
        if safe_title.upper() in WINDOWS_RESERVED_NAMES:
            safe_title = f"_{safe_title}"
        if not safe_title:
            raise ValueError(f"O título remoto {artifact.title!r} não pode ser usado como nome de arquivo.")
        directory = self.root / artifact.kind.directory if artifact.kind.directory else self.root
        target = (directory / f"{safe_title}{artifact.kind.extension}").resolve()
        if self.root != target and self.root not in target.parents:
            raise ValueError(f"O título aponta para fora da pasta escolhida: {artifact.title!r}")
        return target

    @staticmethod
    def _directory_key(name: str) -> str:
        decomposed = unicodedata.normalize("NFKD", name)
        without_accents = "".join(
            character for character in decomposed
            if not unicodedata.combining(character)
        )
        return "".join(character for character in without_accents.casefold() if character.isalnum())

    def _canonical_artifact_path(self, path: Path) -> Path:
        """Projeta uma pasta equivalente para o nome canônico sem alterar o disco."""
        try:
            relative = path.resolve().relative_to(self.root)
        except ValueError:
            return path
        if len(relative.parts) < 2:
            return path
        first = relative.parts[0]
        for kind in ArtifactKind:
            canonical = kind.directory
            if canonical and self._is_artifact_directory(kind, first):
                return self.root / canonical / Path(*relative.parts[1:])
        return path

    def _is_artifact_directory(self, kind: ArtifactKind, name: str) -> bool:
        accepted = {kind.directory, *DIRECTORY_ALIASES.get(kind, set())}
        key = self._directory_key(name)
        return bool(kind.directory and any(self._directory_key(item) == key for item in accepted))

    def _artifact_directory_plan(self, kinds: Iterable[ArtifactKind]) -> list[tuple[Path, Path]]:
        if not self.root.is_dir():
            return []
        children = [child for child in self.root.iterdir() if child.is_dir()]
        plan: list[tuple[Path, Path]] = []
        for kind in set(kinds):
            canonical_name = kind.directory
            if not canonical_name:
                continue
            canonical = self.root / canonical_name
            if canonical.is_symlink():
                raise ValueError(f"A pasta canônica não pode ser um link simbólico: {canonical}")
            for child in children:
                if child.name != canonical_name and self._is_artifact_directory(kind, child.name):
                    if child.is_symlink():
                        raise ValueError(f"A pasta equivalente não pode ser um link simbólico: {child}")
                    plan.append((child, canonical))
        return plan

    def directory_changes(self, kinds: Iterable[ArtifactKind]) -> dict[ArtifactKind, tuple[str, ...]]:
        result: dict[ArtifactKind, list[str]] = defaultdict(list)
        for source, target in self._artifact_directory_plan(kinds):
            kind = next(item for item in ArtifactKind if item.directory == target.name)
            action = "renomeada para" if not target.exists() else "consolidada em"
            result[kind].append(
                f'A pasta local "{source.name}" será {action} "{target.name}" ao sincronizar.'
            )
        return {kind: tuple(messages) for kind, messages in result.items()}

    @staticmethod
    def _merge_conflicts(source: Path, target: Path) -> list[Path]:
        conflicts: list[Path] = []
        for item in source.rglob("*"):
            relative = item.relative_to(source)
            destination = target / relative
            if item.is_symlink() or destination.is_symlink():
                conflicts.append(relative)
                continue
            if not target.exists():
                continue
            if not destination.exists():
                continue
            if item.is_dir() and destination.is_dir():
                continue
            if item.is_file() and destination.is_file() and item.read_bytes() == destination.read_bytes():
                continue
            conflicts.append(relative)
        return conflicts

    @staticmethod
    def _merge_directory(source: Path, target: Path) -> None:
        if not target.exists():
            source.rename(target)
            return
        for item in sorted(source.rglob("*"), key=lambda path: len(path.parts)):
            relative = item.relative_to(source)
            destination = target / relative
            if item.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
            elif destination.exists():
                # A preflight já confirmou que os conteúdos são idênticos.
                item.unlink()
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(destination))
        for directory in sorted(
            (path for path in source.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            directory.rmdir()
        source.rmdir()

    def _validate_directory_plan(self, plan: list[tuple[Path, Path]]) -> None:
        conflicts: list[str] = []
        for source, target in plan:
            for relative in self._merge_conflicts(source, target):
                conflicts.append(f"{source.name}/{relative.as_posix()}")
        for index, (source, target) in enumerate(plan):
            for other, other_target in plan[index + 1:]:
                if other_target == target:
                    for relative in self._merge_conflicts(source, other):
                        conflicts.append(f"{source.name}/{relative.as_posix()}")
        if conflicts:
            names = ", ".join(conflicts[:5])
            suffix = "" if len(conflicts) <= 5 else f" e mais {len(conflicts) - 5}"
            raise ValueError(
                "Não foi possível consolidar pastas equivalentes porque existem arquivos "
                f"diferentes no mesmo caminho: {names}{suffix}"
            )

    def _apply_directory_plan(self, plan: list[tuple[Path, Path]]) -> None:
        for source, target in plan:
            self._merge_directory(source, target)

    def _normalize_artifact_directories(self, kinds: Iterable[ArtifactKind]) -> None:
        plan = self._artifact_directory_plan(kinds)
        self._validate_directory_plan(plan)
        self._apply_directory_plan(plan)

    def _local_scripts(self) -> tuple[dict[str, list[Path]], list[str]]:
        """Indexa todos os .groovy abaixo da raiz, independentemente da pasta."""
        found: dict[str, list[Path]] = defaultdict(list)
        errors: list[str] = []

        def report_error(error: OSError) -> None:
            errors.append(str(error))

        for directory, _subdirectories, files in os.walk(self.root, onerror=report_error):
            for filename in files:
                if filename.casefold().endswith((".groovy", ".jrxml")):
                    found[filename.casefold()].append(Path(directory) / filename)
        return dict(found), errors

    def analyze(
        self,
        kinds: Iterable[ArtifactKind],
        progress: Callable[[str], None] | None = None,
    ) -> list[SyncChange]:
        report = progress or (lambda _message: None)
        if hasattr(self.api, "cache_hits"):
            self.api.cache_hits = 0
        if hasattr(self.api, "cache_misses"):
            self.api.cache_misses = 0
        requested: list[tuple[ArtifactKind, dict]] = []
        changes: list[SyncChange] = []
        for kind in kinds:
            report(f"Listando {kind.value}...")
            try:
                kind_summaries = self.api.list_artifact_summaries(kind)
            except Exception as exc:
                changes.append(SyncChange(ChangeKind.ERROR, None, None, str(exc)))
                continue
            requested.extend((kind, summary) for summary in kind_summaries)

        changes.extend(self.analyze_summaries(requested, progress=report))
        return changes

    def remote_filename_key(self, kind: ArtifactKind, title: str) -> str:
        """Retorna o nome local normalizado sem baixar o código-fonte."""
        placeholder = RemoteArtifact(kind, title, "", "", "")
        return self._target(placeholder).name.casefold()

    def analyze_summaries(
        self,
        summaries: Iterable[tuple[ArtifactKind, dict]],
        duplicate_names: set[str] | None = None,
        progress: Callable[[str], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> list[SyncChange]:
        """Baixa e compara somente os resumos solicitados, preservando sua ordem."""
        report = progress or (lambda _message: None)
        requested = list(summaries)
        artifacts: list[RemoteArtifact | None] = []
        fetch_errors: list[str] = []
        for index, (kind, summary) in enumerate(requested, 1):
            if cancelled and cancelled():
                raise RuntimeError("Operação cancelada pelo usuário.")
            title = str(summary.get("titulo") or summary.get("title") or summary.get("nome") or "desconhecido")
            report(f"Carregando {kind.value} {index}/{len(requested)}: {title}")
            try:
                artifacts.append(self.api.fetch_artifact(kind, summary))
                fetch_errors.append("")
            except Exception as exc:
                artifacts.append(RemoteArtifact(kind, title, "", "", ""))
                fetch_errors.append(str(exc))

        local_scripts, scan_errors = self._local_scripts()
        scan_message = "; ".join(scan_errors)
        planned_directories = self.directory_changes(kind for kind, _summary in requested)
        target_names: list[str] = []
        for artifact, error in zip(artifacts, fetch_errors):
            if artifact is None or error:
                continue
            try:
                target_names.append(self._target(artifact).name.casefold())
            except ValueError:
                pass
        duplicates = (
            duplicate_names
            if duplicate_names is not None
            else {name for name, count in Counter(target_names).items() if count > 1}
        )

        changes: list[SyncChange] = []
        for artifact, fetch_error in zip(artifacts, fetch_errors):
            if artifact is None:
                continue
            if fetch_error:
                changes.append(SyncChange(ChangeKind.ERROR, artifact, None, fetch_error))
                continue
            if scan_message:
                changes.append(SyncChange(ChangeKind.ERROR, artifact, self.root, f"Falha ao percorrer o repositório: {scan_message}"))
                continue
            try:
                default_target = self._target(artifact)
                filename_key = default_target.name.casefold()
            except ValueError as exc:
                changes.append(SyncChange(ChangeKind.CONFLICT, artifact, None, str(exc)))
                continue
            if filename_key in duplicates:
                changes.append(
                    SyncChange(
                        ChangeKind.CONFLICT,
                        artifact,
                        default_target,
                        "Mais de um artefato remoto resulta no mesmo arquivo.",
                    )
                )
                continue
            matches = local_scripts.get(filename_key, [])
            if len(matches) > 1:
                projected = {self._canonical_artifact_path(path) for path in matches}
                identical = all(
                    path.is_file() and path.read_bytes() == matches[0].read_bytes()
                    for path in matches[1:]
                )
                if len(projected) != 1 or not identical:
                    locations = ", ".join(str(path.relative_to(self.root)) for path in matches)
                    changes.append(
                        SyncChange(
                            ChangeKind.CONFLICT,
                            artifact,
                            None,
                            f"O arquivo existe em mais de um local: {locations}",
                        )
                    )
                    continue
            existing = matches[0] if matches else default_target
            target = self._canonical_artifact_path(existing)
            if not existing.exists():
                changes.append(
                    SyncChange(
                        ChangeKind.CREATE,
                        artifact,
                        target,
                        directory_changes=planned_directories.get(artifact.kind, ()),
                    )
                )
                continue
            try:
                local = existing.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                changes.append(SyncChange(ChangeKind.ERROR, artifact, target, str(exc)))
                continue
            status = ChangeKind.UNCHANGED if local == artifact.source_code else ChangeKind.UPDATE
            changes.append(
                SyncChange(
                    status,
                    artifact,
                    target,
                    directory_changes=planned_directories.get(artifact.kind, ()),
                )
            )
        return changes

    def apply(
        self,
        changes: Iterable[SyncChange],
        cancelled: Callable[[], bool] | None = None,
        require_directory_preview: bool = False,
    ) -> int:
        selected = list(changes)
        actionable = [
            change for change in selected
            if change.status in (ChangeKind.CREATE, ChangeKind.UPDATE)
            and change.path is not None and change.artifact is not None
        ]
        if not actionable:
            return 0
        directory_plan = self._artifact_directory_plan(
            change.artifact.kind for change in actionable
        )
        if require_directory_preview:
            kinds = {change.artifact.kind for change in actionable}
            actual = {
                message
                for messages in self.directory_changes(kinds).values()
                for message in messages
            }
            previewed = {
                message
                for change in actionable
                for message in change.directory_changes
            }
            if actual != previewed:
                raise ValueError(
                    "As pastas locais mudaram depois da análise. Analise novamente antes de sincronizar."
                )
        self._validate_directory_plan(directory_plan)
        backup_id, manifest = self.backups.prepare(
            self.root,
            actionable,
            directory_moves=directory_plan,
        )
        written = 0
        try:
            self._apply_directory_plan(directory_plan)
            for change in actionable:
                if cancelled and cancelled():
                    raise RuntimeError("Operação cancelada pelo usuário.")
                change.path.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{change.path.name}.", suffix=".tmp", dir=change.path.parent
                )
                temporary = Path(temporary_name)
                try:
                    with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
                        stream.write(change.artifact.source_code)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, change.path)
                    written += 1
                finally:
                    temporary.unlink(missing_ok=True)
            self.backups.mark_applied(backup_id, manifest)
        except Exception:
            self.backups.abort(backup_id, manifest, self.root)
            raise
        self.last_backup_id = backup_id
        return written

    def undo(self, backup_id: str) -> int:
        return self.backups.undo(backup_id, self.root)

