from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

from .models import ArtifactKind, RemoteArtifact


def artifact_cache_dir() -> Path:
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
        return root / "StudioSync" / "cache" / "artifacts"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "StudioSync" / "artifacts"
    root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return root / "studio-sync" / "artifacts"


class ArtifactCache:
    """Cache imutável por contexto, script e revisão."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or artifact_cache_dir()

    def _path(self, context: str, kind: ArtifactKind, script_id: str, revision_id: str) -> Path:
        identity = "\0".join((context, kind.value, script_id, revision_id)).encode()
        return self.root / f"{hashlib.sha256(identity).hexdigest()}.json"

    def get(
        self,
        context: str,
        kind: ArtifactKind,
        title: str,
        script_id: str,
        revision_id: str,
    ) -> RemoteArtifact | None:
        if not script_id or not revision_id:
            return None
        path = self._path(context, kind, script_id, revision_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return None
        source = data.get("source") if isinstance(data, dict) else None
        if not isinstance(source, str):
            return None
        return RemoteArtifact(kind, title, script_id, revision_id, source)

    def put(self, context: str, artifact: RemoteArtifact) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
        except OSError:
            pass
        target = self._path(context, artifact.kind, artifact.script_id, artifact.revision_id)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".artifact-", dir=self.root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"source": artifact.source_code}, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
