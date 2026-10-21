from __future__ import annotations

import json
import unittest
import tempfile
from pathlib import Path

from tools.studio_sync.api import StudioApi
from tools.studio_sync.cache import ArtifactCache
from tools.studio_sync.models import AccessOption, ArtifactKind, SessionCredentials


class FakeResponse:
    def __init__(
        self,
        data: object,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> None:
        self.data = data
        self.headers = headers or {}
        self.content = content if content is not None else json.dumps(data).encode()
        self.status_code = 200

    def json(self) -> object:
        return self.data

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.headers: dict[str, str] = {}
        self.responses = responses
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        return self.responses.pop(0)

    def post(self, url: str, **kwargs: object) -> FakeResponse:
        self.calls.append((url, kwargs))
        return self.responses.pop(0)


class StudioApiTests(unittest.TestCase):
    def test_contract_fixture_fetches_every_supported_artifact_kind(self) -> None:
        fixture_path = Path(__file__).with_name("fixtures") / "studio_artifact.json"
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            for kind in ArtifactKind:
                responses = (
                    [FakeResponse({}, content=b"<?xml version=\"1.0\"?><jasperReport/>")]
                    if kind is ArtifactKind.REPORT
                    else [FakeResponse(fixture["detail"]), FakeResponse(fixture["revision"])]
                )
                session = FakeSession(responses)
                api = StudioApi(
                    SessionCredentials("token", "context"),
                    session=session,  # type: ignore[arg-type]
                    cache=ArtifactCache(Path(directory) / kind.value),
                )
                artifact = api.fetch_artifact(kind, fixture["summary"])
                self.assertEqual(kind, artifact.kind)
                expected = (
                    '<?xml version="1.0"?><jasperReport/>'
                    if kind is ArtifactKind.REPORT
                    else "println 'contrato'"
                )
                self.assertEqual(expected, artifact.source_code)

    def test_downloads_current_report_jrxml(self) -> None:
        session = FakeSession([
            FakeResponse({}, content=b'<?xml version="1.0" encoding="UTF-8"?><jasperReport/>')
        ])
        with tempfile.TemporaryDirectory() as directory:
            api = StudioApi(
                SessionCredentials("token", "context"),
                session=session,  # type: ignore[arg-type]
                cache=ArtifactCache(Path(directory)),
            )
            artifact = api.fetch_artifact(
                ArtifactKind.REPORT,
                {"titulo": "Relatório", "referencia": {"id": 1256657, "revisao": 77}},
            )
        self.assertEqual(ArtifactKind.REPORT, artifact.kind)
        self.assertEqual("1256657", artifact.script_id)
        self.assertIn("<jasperReport/>", artifact.source_code)
        self.assertEqual(
            "https://plataforma-relatorios.betha.cloud/relatorios/v1/api/relatorios/1256657/download",
            session.calls[0][0],
        )
        self.assertEqual([], session.calls[0][1]["json"])

    def test_reuses_cached_artifact_revision_without_http_requests(self) -> None:
        summary = {
            "titulo": "Componente",
            "referencia": {"id": 100, "revisao": 200},
        }
        with tempfile.TemporaryDirectory() as directory:
            cache = ArtifactCache(Path(directory))
            first_session = FakeSession(
                [
                    FakeResponse({"referencia": {"id": 100, "revisao": 200}}),
                    FakeResponse({"codigoFonte": "println 'cache'"}),
                ]
            )
            first = StudioApi(
                SessionCredentials("token", "context"),
                session=first_session,  # type: ignore[arg-type]
                cache=cache,
            )
            self.assertEqual(
                "println 'cache'", first.fetch_artifact(ArtifactKind.COMPONENT, summary).source_code
            )
            self.assertEqual(1, first.cache_misses)

            second_session = FakeSession([])
            second = StudioApi(
                SessionCredentials("token", "context"),
                session=second_session,  # type: ignore[arg-type]
                cache=cache,
            )
            self.assertEqual(
                "println 'cache'", second.fetch_artifact(ArtifactKind.COMPONENT, summary).source_code
            )
            self.assertEqual(1, second.cache_hits)
            self.assertEqual([], second_session.calls)

    def test_parses_nested_accesses(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    {
                        "content": [
                            {
                                "id": "access-1",
                                "entity": {"id": 4746, "name": "Entidade Exemplo"},
                                "database": {"id": 4529, "name": "Produção"},
                            }
                        ]
                    }
                )
            ]
        )
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        options = api.list_accesses()
        self.assertEqual(1, len(options))
        self.assertEqual("database:4529,entity:4746", options[0].context)
        self.assertEqual("Entidade Exemplo", options[0].label)

    def test_resolves_numeric_entity_and_system_names(self) -> None:
        session = FakeSession(
            [
                FakeResponse([{"entity": "4746", "database": "4529", "system": "151"}]),
                FakeResponse([{"id": 4746, "name": "BETHA SISTEMAS - EXTENSÕES - PR"}]),
                FakeResponse([{"id": 151, "name": "Prestação de Contas"}]),
            ]
        )
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        option = api.list_accesses()[0]
        self.assertEqual("BETHA SISTEMAS - EXTENSÕES - PR", option.label)
        self.assertEqual("Prestação de Contas", option.system_name)

    def test_quick_access_refresh_skips_name_queries_and_limits_timeout(self) -> None:
        session = FakeSession(
            [FakeResponse([{"entity": "4746", "database": "4529", "system": "151"}])]
        )
        api = StudioApi(
            SessionCredentials("token", "context"),
            timeout=30,
            session=session,  # type: ignore[arg-type]
        )

        option = api.list_accesses(quick=True)[0]

        self.assertEqual("Entidade 4746", option.label)
        self.assertEqual("Sistema não identificado", option.system_name)
        self.assertEqual(1, len(session.calls))
        self.assertEqual(10, session.calls[0][1]["timeout"])

    def test_expands_system_list_for_one_entity(self) -> None:
        session = FakeSession(
            [
                FakeResponse([{"entity": 4746, "database": 4529, "systems": [78, 103, 151]}]),
                FakeResponse([{"id": 4746, "name": "Entidade completa"}]),
                FakeResponse([
                    {"id": 78, "name": "Contratos"},
                    {"id": 103, "name": "Orquestrador"},
                    {"id": 151, "name": "Prestação de Contas"},
                ]),
            ]
        )
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        options = api.list_accesses()
        self.assertEqual(3, len(options))
        self.assertEqual(
            ["Contratos", "Orquestrador", "Prestação de Contas"],
            sorted(option.system_name for option in options),
        )

    def test_resolves_system_map_response(self) -> None:
        session = FakeSession(
            [
                FakeResponse([{"entity": 4746, "database": 4529, "systems": [78, 151]}]),
                FakeResponse([{"id": 4746, "name": "Entidade"}]),
                FakeResponse({"78": "Contratos", "151": "Prestação de Contas"}),
            ]
        )
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        self.assertEqual(
            ["Contratos", "Prestação de Contas"],
            sorted(option.system_name for option in api.list_accesses()),
        )

    def test_resolves_system_value_label_response(self) -> None:
        session = FakeSession(
            [
                FakeResponse([{"entity": 4746, "database": 4529, "systems": [103]}]),
                FakeResponse([{"id": 4746, "name": "Entidade"}]),
                FakeResponse([{"value": 103, "label": "Orquestrador"}]),
            ]
        )
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        self.assertEqual("Orquestrador", api.list_accesses()[0].system_name)

    def test_resolves_system_numeric_key_with_nested_value(self) -> None:
        session = FakeSession(
            [
                FakeResponse([{"entity": 4746, "database": 4529, "systems": [151]}]),
                FakeResponse([{"id": 4746, "name": "Entidade"}]),
                FakeResponse({"151": {"denominacao": "Prestação de Contas", "ativo": True}}),
            ]
        )
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        self.assertEqual("Prestação de Contas", api.list_accesses()[0].system_name)

    def test_resolves_system_from_unknown_id_and_name_fields(self) -> None:
        session = FakeSession(
            [
                FakeResponse([{"entity": 4746, "database": 4529, "systems": [151]}]),
                FakeResponse([{"id": 4746, "name": "Entidade"}]),
                FakeResponse([{"codigoSistema": 151, "denominacao": "Prestação de Contas"}]),
            ]
        )
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        self.assertEqual("Prestação de Contas", api.list_accesses()[0].system_name)

    def test_parses_scalar_accesses(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    [
                        {
                            "id": "access-1",
                            "entity": 4746,
                            "database": 4529,
                            "entityName": "Entidade Exemplo",
                        }
                    ]
                )
            ]
        )
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        option = api.list_accesses()[0]
        self.assertEqual("4746", option.entity_id)
        self.assertEqual("4529", option.database_id)

    def test_lists_systems_from_selected_entity_permissions(self) -> None:
        session = FakeSession(
            [
                FakeResponse([
                    {"id": 78, "name": "Contratos"},
                    {"id": 151, "name": "Prestação de Contas"},
                ]),
            ]
        )
        api = StudioApi(SessionCredentials("token", "initial-context"), session=session)  # type: ignore[arg-type]
        option = api.list_permitted_systems(
            AccessOption(label="Entidade", entity_id="4746", database_id="4529")
        )
        self.assertEqual(["Contratos", "Prestação de Contas"], [item.system_name for item in option])
        self.assertIn("/access/ZGF0YWJhc2U6NDUyOSxlbnRpdHk6NDc0Ng%3D%3D/systems", session.calls[0][0])
        self.assertEqual(
            {"includeCurrentAsSourceSystem": "true"}, session.calls[0][1]["params"]
        )

    def test_selects_system_specific_user_access_without_context_request(self) -> None:
        session = FakeSession([])
        api = StudioApi(SessionCredentials("token", "initial-context"), session=session)  # type: ignore[arg-type]
        selected = api.select_access(
            AccessOption(
                label="Entidade",
                entity_id="4746",
                database_id="4529",
                system_id="103",
                access_id="access-contratos",
                user_access="contratos-context",
            )
        )
        self.assertEqual("contratos-context", selected)
        self.assertEqual("contratos-context", session.headers["user-access"])
        self.assertEqual([], session.calls)

    def test_uses_license_id_as_system_user_access(self) -> None:
        session = FakeSession(
            [
                FakeResponse(
                    [
                        {
                            "id": "access-contratos",
                            "licenseId": "license-context-103",
                            "system": 103,
                            "values": {"entity": "4746", "database": "4529"},
                        }
                    ]
                ),
                FakeResponse([{"id": 4746, "name": "Entidade"}]),
                FakeResponse([{"id": 103, "name": "Contratos"}]),
            ]
        )
        api = StudioApi(SessionCredentials("token", "initial-context"), session=session)  # type: ignore[arg-type]
        option = api.list_accesses()[0]
        self.assertEqual("license-context-103", option.user_access)

    def test_parses_access_wrapped_in_source_system(self) -> None:
        session = FakeSession(
            [FakeResponse({"content": [{"access": {"entityId": 4746}, "sourceSystem": {"databaseId": 4529}, "entityName": "Entidade"}]})]
        )
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        option = api.list_accesses()[0]
        self.assertEqual("database:4529,entity:4746", option.context)

    def test_parses_encoded_context(self) -> None:
        session = FakeSession(
            [FakeResponse([{"context": "ZGF0YWJhc2U6NDUyOSxlbnRpdHk6NDc0Ng==", "entityName": "Entidade"}])]
        )
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        option = api.list_accesses()[0]
        self.assertEqual("database:4529,entity:4746", option.context)

    def test_paginates_using_returned_item_count(self) -> None:
        first = {"content": [{"titulo": "A"}, {"titulo": "B"}], "hasNext": True}
        second = {"content": [{"titulo": "C"}], "hasNext": False}
        session = FakeSession([FakeResponse(first), FakeResponse(second)])
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]
        summaries = api.list_artifact_summaries(ArtifactKind.JOB)
        self.assertEqual(["A", "B", "C"], [item["titulo"] for item in summaries])
        self.assertEqual(2, session.calls[1][1]["params"]["offset"])  # type: ignore[index]

    def test_filters_each_supported_artifact_kind_with_official_api_value(self) -> None:
        session = FakeSession([
            FakeResponse({"content": [], "hasNext": False}) for _kind in ArtifactKind
        ])
        api = StudioApi(SessionCredentials("token", "context"), session=session)  # type: ignore[arg-type]

        for kind in ArtifactKind:
            api.list_artifact_summaries(kind)

        filters = [call[1]["params"]["filter"] for call in session.calls]  # type: ignore[index]
        self.assertEqual(
            [
                "tipo = 'SCRIPT' and propriedades in(new Propriedade('tipoScript', 'JOB'))",
                "tipo = 'SCRIPT' and propriedades in(new Propriedade('tipoScript', 'COMPONENTE'))",
                "tipo = 'SCRIPT' and propriedades in(new Propriedade('tipoScript', 'CRITICA'))",
                "tipo = 'SCRIPT' and propriedades in(new Propriedade('tipoScript', 'FONTE_DINAMICA'))",
                "tipo = 'RELATORIO'",
            ],
            filters,
        )


if __name__ == "__main__":
    unittest.main()
