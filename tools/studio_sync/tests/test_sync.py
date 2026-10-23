from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.studio_sync.backup import BackupStore
from tools.studio_sync.models import ArtifactKind, ChangeKind, RemoteArtifact
from tools.studio_sync.sync import Synchronizer


class FakeApi:
    def __init__(self, artifacts: dict[ArtifactKind, list[RemoteArtifact]]) -> None:
        self.artifacts = artifacts
        self.fetched: list[str] = []

    def list_artifact_summaries(self, kind: ArtifactKind) -> list[dict[str, str]]:
        return [{"titulo": item.title} for item in self.artifacts.get(kind, [])]

    def fetch_artifact(self, kind: ArtifactKind, summary: dict[str, str]) -> RemoteArtifact:
        self.fetched.append(summary["titulo"])
        return next(item for item in self.artifacts[kind] if item.title == summary["titulo"])


class SynchronizerTests(unittest.TestCase):
    def test_analyzes_only_requested_page_summaries(self) -> None:
        artifacts = [
            RemoteArtifact(ArtifactKind.JOB, f"Script {index}", str(index), str(index), "codigo")
            for index in range(1, 6)
        ]
        api = FakeApi({ArtifactKind.JOB: artifacts})
        page = [(ArtifactKind.JOB, {"titulo": item.title}) for item in artifacts[2:4]]
        with tempfile.TemporaryDirectory() as directory:
            changes = Synchronizer(api, Path(directory)).analyze_summaries(page)  # type: ignore[arg-type]

        self.assertEqual(["Script 3", "Script 4"], api.fetched)
        self.assertEqual(2, len(changes))

    def test_analyzes_and_applies_all_artifact_kinds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "Existente.groovy").write_text("antigo", encoding="utf-8")
            artifacts = {
                ArtifactKind.JOB: [
                    RemoteArtifact(ArtifactKind.JOB, "Existente", "1", "10", "novo"),
                    RemoteArtifact(ArtifactKind.JOB, "Novo", "2", "20", "codigo"),
                ],
                ArtifactKind.COMPONENT: [
                    RemoteArtifact(ArtifactKind.COMPONENT, "Componente", "3", "30", "componente")
                ],
                ArtifactKind.CRITIQUE: [
                    RemoteArtifact(ArtifactKind.CRITIQUE, "Critica", "4", "40", "critica")
                ],
                ArtifactKind.DYNAMIC_SOURCE: [
                    RemoteArtifact(
                        ArtifactKind.DYNAMIC_SOURCE, "Fonte", "5", "50", "fonte dinamica"
                    )
                ],
                ArtifactKind.REPORT: [
                    RemoteArtifact(
                        ArtifactKind.REPORT, "Ata", "6", "60", "<?xml version='1.0'?><jasperReport/>"
                    )
                ],
            }
            synchronizer = Synchronizer(
                FakeApi(artifacts), root, BackupStore(root / ".test-backups")  # type: ignore[arg-type]
            )
            changes = synchronizer.analyze(list(ArtifactKind))

            self.assertEqual(
                [
                    ChangeKind.UPDATE,
                    ChangeKind.CREATE,
                    ChangeKind.CREATE,
                    ChangeKind.CREATE,
                    ChangeKind.CREATE,
                    ChangeKind.CREATE,
                ],
                [change.status for change in changes],
            )
            self.assertEqual(6, synchronizer.apply(changes))
            self.assertEqual("novo", (root / "Existente.groovy").read_text(encoding="utf-8"))
            self.assertEqual("codigo", (root / "Novo.groovy").read_text(encoding="utf-8"))
            self.assertEqual(
                "componente",
                (root / "Componentes" / "Componente.groovy").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "critica",
                (root / "Criticas" / "Critica.groovy").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "fonte dinamica",
                (root / "FontesDinamicas" / "Fonte.groovy").read_text(encoding="utf-8"),
            )
            self.assertEqual(
                "<?xml version='1.0'?><jasperReport/>",
                (root / "Relatorios" / "Ata.jrxml").read_text(encoding="utf-8"),
            )

    def test_compares_report_with_existing_jrxml(self) -> None:
        artifact = RemoteArtifact(
            ArtifactKind.REPORT, "Relatório", "7", "70", "<?xml version='1.0'?><jasperReport/>"
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "Relatorios"
            reports.mkdir()
            local = reports / "Relatório.jrxml"
            local.write_text(artifact.source_code, encoding="utf-8")
            changes = Synchronizer(
                FakeApi({ArtifactKind.REPORT: [artifact]}), root  # type: ignore[arg-type]
            ).analyze([ArtifactKind.REPORT])
        self.assertEqual(ChangeKind.UNCHANGED, changes[0].status)
        self.assertEqual(local, changes[0].path)

    def test_sanitizes_path_separator_in_title(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.JOB, "Abertura/Reabertura", "1", "2", "codigo")
        api = FakeApi({ArtifactKind.JOB: [artifact]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            changes = Synchronizer(api, root).analyze([ArtifactKind.JOB])  # type: ignore[arg-type]
            self.assertEqual(ChangeKind.CREATE, changes[0].status)
            self.assertEqual(root / "Abertura - Reabertura.groovy", changes[0].path)

    def test_rejects_title_without_usable_characters(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.JOB, "...", "1", "2", "codigo")
        api = FakeApi({ArtifactKind.JOB: [artifact]})
        with tempfile.TemporaryDirectory() as directory:
            changes = Synchronizer(api, Path(directory)).analyze([ArtifactKind.JOB])  # type: ignore[arg-type]
        self.assertEqual(ChangeKind.CONFLICT, changes[0].status)

    def test_detects_duplicate_file_names(self) -> None:
        artifacts = [
            RemoteArtifact(ArtifactKind.JOB, "Duplicado", "1", "10", "a"),
            RemoteArtifact(ArtifactKind.JOB, "Duplicado", "2", "20", "b"),
        ]
        with tempfile.TemporaryDirectory() as directory:
            changes = Synchronizer(
                FakeApi({ArtifactKind.JOB: artifacts}), Path(directory)  # type: ignore[arg-type]
            ).analyze([ArtifactKind.JOB])
        self.assertEqual([ChangeKind.CONFLICT, ChangeKind.CONFLICT], [item.status for item in changes])

    def test_finds_job_inside_components_folder(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.JOB, "JobMovido", "1", "10", "novo")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "Componentes" / "JobMovido.groovy"
            existing.parent.mkdir()
            existing.write_text("antigo", encoding="utf-8")
            synchronizer = Synchronizer(
                FakeApi({ArtifactKind.JOB: [artifact]}),
                root,
                BackupStore(root / ".test-backups"),  # type: ignore[arg-type]
            )
            changes = synchronizer.analyze([ArtifactKind.JOB])
            self.assertEqual(ChangeKind.UPDATE, changes[0].status)
            self.assertEqual(existing, changes[0].path)
            synchronizer.apply(changes)
            self.assertEqual("novo", existing.read_text(encoding="utf-8"))
            self.assertFalse((root / "JobMovido.groovy").exists())

    def test_finds_component_in_any_nested_folder(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.COMPONENT, "ComponenteMovido", "1", "10", "igual")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            existing = root / "scripts" / "internos" / "ComponenteMovido.groovy"
            existing.parent.mkdir(parents=True)
            existing.write_text("igual", encoding="utf-8")
            changes = Synchronizer(
                FakeApi({ArtifactKind.COMPONENT: [artifact]}), root  # type: ignore[arg-type]
            ).analyze([ArtifactKind.COMPONENT])
            self.assertEqual(ChangeKind.UNCHANGED, changes[0].status)
            self.assertEqual(existing, changes[0].path)

    def test_reports_conflict_when_local_name_exists_more_than_once(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.JOB, "Repetido", "1", "10", "codigo")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for folder in (root / "scripts", root / "Componentes"):
                folder.mkdir()
                (folder / "Repetido.groovy").write_text("codigo", encoding="utf-8")
            changes = Synchronizer(
                FakeApi({ArtifactKind.JOB: [artifact]}), root  # type: ignore[arg-type]
            ).analyze([ArtifactKind.JOB])
            self.assertEqual(ChangeKind.CONFLICT, changes[0].status)
            self.assertIn("mais de um local", changes[0].message)

    def test_reuses_and_renames_equivalent_artifact_directory(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.COMPONENT, "Existente", "1", "10", "novo")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variant = root / "componentes"
            variant.mkdir()
            (variant / "Existente.groovy").write_text("antigo", encoding="utf-8")
            synchronizer = Synchronizer(
                FakeApi({ArtifactKind.COMPONENT: [artifact]}),
                root,
                BackupStore(root / ".test-backups"),  # type: ignore[arg-type]
            )

            changes = synchronizer.analyze([ArtifactKind.COMPONENT])

            self.assertEqual(ChangeKind.UPDATE, changes[0].status)
            self.assertEqual(root / "Componentes" / "Existente.groovy", changes[0].path)
            synchronizer.apply(changes)
            self.assertFalse(variant.exists())
            self.assertEqual(
                "novo",
                (root / "Componentes" / "Existente.groovy").read_text(encoding="utf-8"),
            )

    def test_recognizes_english_components_alias_and_previews_the_rename(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.COMPONENT, "Novo", "1", "10", "codigo")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "Components"
            legacy.mkdir()
            (legacy / "Legado.groovy").write_text("legado", encoding="utf-8")
            synchronizer = Synchronizer(
                FakeApi({ArtifactKind.COMPONENT: [artifact]}),
                root,
                BackupStore(root / ".test-backups"),  # type: ignore[arg-type]
            )

            changes = synchronizer.analyze([ArtifactKind.COMPONENT])

            self.assertEqual(root / "Componentes" / "Novo.groovy", changes[0].path)
            self.assertEqual(
                ('A pasta local "Components" será renomeada para "Componentes" ao sincronizar.',),
                changes[0].directory_changes,
            )
            synchronizer.apply(changes)
            self.assertFalse(legacy.exists())
            self.assertEqual("legado", (root / "Componentes" / "Legado.groovy").read_text())

    def test_requires_new_analysis_when_directory_plan_changes(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.COMPONENT, "Novo", "1", "10", "codigo")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            synchronizer = Synchronizer(
                FakeApi({ArtifactKind.COMPONENT: [artifact]}),
                root,
                BackupStore(root / ".test-backups"),  # type: ignore[arg-type]
            )
            changes = synchronizer.analyze([ArtifactKind.COMPONENT])
            legacy = root / "Components"
            legacy.mkdir()
            (legacy / "Legado.groovy").write_text("legado", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Analise novamente"):
                synchronizer.apply(changes, require_directory_preview=True)

            self.assertTrue(legacy.exists())
            self.assertFalse((root / "Componentes").exists())

    def test_consolidates_accented_and_canonical_directories_without_data_loss(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.DYNAMIC_SOURCE, "Nova", "1", "10", "codigo")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / "FontesDinamicas"
            variant = root / "Fontes Dinâmicas"
            canonical.mkdir()
            variant.mkdir()
            (canonical / "Canonica.groovy").write_text("canonica", encoding="utf-8")
            (variant / "Legada.groovy").write_text("legada", encoding="utf-8")
            synchronizer = Synchronizer(
                FakeApi({ArtifactKind.DYNAMIC_SOURCE: [artifact]}),
                root,
                BackupStore(root / ".test-backups"),  # type: ignore[arg-type]
            )

            changes = synchronizer.analyze([ArtifactKind.DYNAMIC_SOURCE])
            synchronizer.apply(changes)

            self.assertFalse(variant.exists())
            self.assertEqual("canonica", (canonical / "Canonica.groovy").read_text(encoding="utf-8"))
            self.assertEqual("legada", (canonical / "Legada.groovy").read_text(encoding="utf-8"))
            self.assertEqual("codigo", (canonical / "Nova.groovy").read_text(encoding="utf-8"))

    def test_refuses_to_merge_different_files_at_the_same_relative_path(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.CRITIQUE, "Nova", "1", "10", "codigo")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            canonical = root / "Criticas"
            variant = root / "Críticas"
            canonical.mkdir()
            variant.mkdir()
            (canonical / "Duplicada.groovy").write_text("a", encoding="utf-8")
            (variant / "Duplicada.groovy").write_text("b", encoding="utf-8")
            synchronizer = Synchronizer(
                FakeApi({ArtifactKind.CRITIQUE: [artifact]}),
                root,
                BackupStore(root / ".test-backups"),  # type: ignore[arg-type]
            )
            changes = synchronizer.analyze([ArtifactKind.CRITIQUE])

            with self.assertRaisesRegex(ValueError, "arquivos diferentes"):
                synchronizer.apply(changes)

            self.assertTrue(canonical.exists())
            self.assertTrue(variant.exists())
            self.assertFalse((canonical / "Nova.groovy").exists())

    def test_refuses_conflicts_between_multiple_variants_before_renaming_any_folder(self) -> None:
        artifact = RemoteArtifact(ArtifactKind.REPORT, "Novo", "1", "10", "jrxml")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "Relatórios"
            second = root / "RELATORIOS"
            first.mkdir()
            second.mkdir()
            (first / "Duplicado.jrxml").write_text("a", encoding="utf-8")
            (second / "Duplicado.jrxml").write_text("b", encoding="utf-8")
            synchronizer = Synchronizer(
                FakeApi({ArtifactKind.REPORT: [artifact]}),
                root,
                BackupStore(root / ".test-backups"),  # type: ignore[arg-type]
            )
            changes = synchronizer.analyze([ArtifactKind.REPORT])

            with self.assertRaisesRegex(ValueError, "arquivos diferentes"):
                synchronizer.apply(changes)

            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertFalse((root / "Relatorios").exists())


if __name__ == "__main__":
    unittest.main()
