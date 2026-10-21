from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.studio_sync.backup import BackupError, BackupStore
from tools.studio_sync.models import ArtifactKind, ChangeKind, RemoteArtifact, SyncChange
from tools.studio_sync.sync import Synchronizer


class FailingBackupStore(BackupStore):
    def mark_applied(self, backup_id: str, manifest: dict[str, object]) -> None:
        raise OSError("falha simulada ao finalizar o snapshot")


class BackupTests(unittest.TestCase):
    def test_undo_restores_updated_file_and_removes_created_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            existing = repository / "Existente.groovy"
            created = repository / "Novo.groovy"
            existing.write_text("antes", encoding="utf-8")
            changes = [
                SyncChange(
                    ChangeKind.UPDATE,
                    RemoteArtifact(ArtifactKind.JOB, "Existente", "1", "1", "depois"),
                    existing,
                ),
                SyncChange(
                    ChangeKind.CREATE,
                    RemoteArtifact(ArtifactKind.JOB, "Novo", "2", "1", "novo"),
                    created,
                ),
            ]
            synchronizer = Synchronizer(
                None, repository, BackupStore(base / "backups")  # type: ignore[arg-type]
            )

            self.assertEqual(2, synchronizer.apply(changes))
            self.assertEqual("depois", existing.read_text(encoding="utf-8"))
            self.assertTrue(created.exists())
            self.assertEqual(2, synchronizer.undo(synchronizer.last_backup_id))
            self.assertEqual("antes", existing.read_text(encoding="utf-8"))
            self.assertFalse(created.exists())
            self.assertEqual("", synchronizer.backups.latest_applied(repository))

    def test_undo_refuses_to_overwrite_a_later_user_edit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            target = repository / "Arquivo.groovy"
            target.write_text("antes", encoding="utf-8")
            change = SyncChange(
                ChangeKind.UPDATE,
                RemoteArtifact(ArtifactKind.JOB, "Arquivo", "1", "1", "sincronizado"),
                target,
            )
            synchronizer = Synchronizer(
                None, repository, BackupStore(base / "backups")  # type: ignore[arg-type]
            )
            synchronizer.apply([change])
            target.write_text("edição posterior", encoding="utf-8")

            with self.assertRaisesRegex(BackupError, "mudaram depois"):
                synchronizer.undo(synchronizer.last_backup_id)
            self.assertEqual("edição posterior", target.read_text(encoding="utf-8"))
            self.assertEqual(
                synchronizer.last_backup_id,
                synchronizer.backups.latest_applied(repository),
            )

    def test_apply_rolls_back_every_written_file_if_snapshot_cannot_be_finalized(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            repository = base / "repository"
            repository.mkdir()
            existing = repository / "Existente.groovy"
            created = repository / "Novo.groovy"
            existing.write_text("antes", encoding="utf-8")
            changes = [
                SyncChange(
                    ChangeKind.UPDATE,
                    RemoteArtifact(ArtifactKind.JOB, "Existente", "1", "1", "depois"),
                    existing,
                ),
                SyncChange(
                    ChangeKind.CREATE,
                    RemoteArtifact(ArtifactKind.JOB, "Novo", "2", "1", "novo"),
                    created,
                ),
            ]
            synchronizer = Synchronizer(
                None, repository, FailingBackupStore(base / "backups")  # type: ignore[arg-type]
            )

            with self.assertRaisesRegex(OSError, "falha simulada"):
                synchronizer.apply(changes)
            self.assertEqual("antes", existing.read_text(encoding="utf-8"))
            self.assertFalse(created.exists())
            self.assertEqual("", synchronizer.last_backup_id)


if __name__ == "__main__":
    unittest.main()
