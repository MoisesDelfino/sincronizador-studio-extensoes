from __future__ import annotations

import os
import re
import tempfile
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
            target = matches[0] if matches else default_target
            if not target.exists():
                changes.append(SyncChange(ChangeKind.CREATE, artifact, target))
                continue
            try:
                local = target.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                changes.append(SyncChange(ChangeKind.ERROR, artifact, target, str(exc)))
                continue
            status = ChangeKind.UNCHANGED if local == artifact.source_code else ChangeKind.UPDATE
            changes.append(SyncChange(status, artifact, target))
        return changes

    def apply(
        self,
        changes: Iterable[SyncChange],
        cancelled: Callable[[], bool] | None = None,
    ) -> int:
        actionable = [
            change for change in changes
            if change.status in (ChangeKind.CREATE, ChangeKind.UPDATE)
            and change.path is not None and change.artifact is not None
        ]
        if not actionable:
            return 0
        backup_id, manifest = self.backups.prepare(self.root, actionable)
        written = 0
        try:
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

