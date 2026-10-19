from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ArtifactKind(str, Enum):
    JOB = "JOB"
    COMPONENT = "COMPONENTE"

    @property
    def directory(self) -> str:
        return "" if self is ArtifactKind.JOB else "Componentes"


class ChangeKind(str, Enum):
    CREATE = "CRIAR"
    UPDATE = "ATUALIZAR"
    UNCHANGED = "INALTERADO"
    CONFLICT = "CONFLITO"
    ERROR = "ERRO"


@dataclass(frozen=True)
class SessionCredentials:
    access_token: str
    user_access: str
    selected_entity_id: str = ""
    selected_database_id: str = ""


@dataclass(frozen=True)
class AccessOption:
    label: str
    entity_id: str
    database_id: str
    system_id: str = ""
    system_name: str = "Sistema não identificado"
    access_id: str = ""
    user_access: str = ""

    @property
    def context(self) -> str:
        return f"database:{self.database_id},entity:{self.entity_id}"


@dataclass(frozen=True)
class RemoteArtifact:
    kind: ArtifactKind
    title: str
    script_id: str
    revision_id: str
    source_code: str


@dataclass(frozen=True)
class SyncChange:
    status: ChangeKind
    artifact: RemoteArtifact | None
    path: Path | None
    message: str = ""

