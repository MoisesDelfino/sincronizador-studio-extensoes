from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import Mock, patch

from tools.studio_sync.api import SessionExpiredError
from tools.studio_sync.instance import running_instance_url
from tools.studio_sync.models import AccessOption
from tools.studio_sync.web import (
    AppState,
    Handler,
    STATIC,
    StaleOperationError,
    run,
)


class WebSmokeTests(unittest.TestCase):
    def test_deve_reconhecer_servidor_studio_registrado(self) -> None:
        # Dado que o registro aponta para uma instância válida do Studio Sync
        with TemporaryDirectory() as directory:
            runtime = Path(directory) / "server.json"
            runtime.write_text('{"port": 43123}', encoding="utf-8")
            response = Mock(
                status=200,
                headers={"Server": "StudioSync/0.2 Python/3"},
            )
            response.read.return_value = b'{"authenticated": true}'
            context = Mock()
            context.__enter__ = Mock(return_value=response)
            context.__exit__ = Mock(return_value=False)

            # Quando o registro é verificado, então a URL existente é reutilizada
            with (
                patch("tools.studio_sync.instance.runtime_file", return_value=runtime),
                patch("tools.studio_sync.instance.urllib.request.urlopen", return_value=context),
            ):
                self.assertEqual("http://127.0.0.1:43123", running_instance_url())

    def test_deve_reabrir_instancia_existente_sem_perder_sessao(self) -> None:
        # Dado que a aplicação continua executando após a guia ser fechada
        url = "http://127.0.0.1:43123"

        # Quando o usuário abre a ferramenta novamente, então a mesma instância é reaberta
        with (
            patch("tools.studio_sync.web.running_instance_url", return_value=url),
            patch("tools.studio_sync.web.webbrowser.open") as open_browser,
            patch("tools.studio_sync.web.ThreadingHTTPServer") as server,
        ):
            run()

        open_browser.assert_called_once_with(url)
        server.assert_not_called()

    def test_deve_remover_registro_da_instancia_quando_servidor_encerrar(self) -> None:
        # Dado que não existe instância anterior e um novo servidor será iniciado
        with TemporaryDirectory() as directory:
            runtime = Path(directory) / "server.json"
            server = Mock(server_port=43124)

            # Quando o servidor encerra, então o registro não permanece apontando para processo morto
            with (
                patch("tools.studio_sync.web.running_instance_url", return_value=""),
                patch("tools.studio_sync.instance.runtime_file", return_value=runtime),
                patch("tools.studio_sync.web.ThreadingHTTPServer", return_value=server),
                patch("tools.studio_sync.web.threading.Timer"),
            ):
                run()

            server.serve_forever.assert_called_once()
            server.server_close.assert_called_once()
            self.assertFalse(runtime.exists())

    def test_deve_deslogar_quando_api_informar_sessao_expirada(self) -> None:
        # Dado que existe uma sessão com dados transitórios carregados
        state = AppState()
        state.api = Mock()
        state.user = "Usuário"
        state.accesses = [AccessOption("Entidade", "2", "20", "56", "Contratos")]
        state.summaries = [Mock()]
        state.changes = [Mock()]
        handler = object.__new__(Handler)
        handler.path = "/api/accesses"
        handler.refresh_accesses = Mock(
            side_effect=SessionExpiredError("Sessão expirada ou acesso não autorizado.")
        )
        handler.send_json = Mock()

        # Quando um endpoint detecta a expiração, então a aplicação volta ao estado deslogado
        with patch("tools.studio_sync.web.STATE", state):
            handler.do_POST()

        self.assertFalse(state.public()["authenticated"])
        self.assertEqual([], state.accesses)
        self.assertEqual([], state.summaries)
        self.assertEqual([], state.changes)
        self.assertTrue(state.cancelled())
        handler.send_json.assert_called_once_with(
            {"error": "Sessão expirada ou acesso não autorizado."}, 400
        )

    def test_deve_manter_sessao_quando_erro_nao_for_de_autorizacao(self) -> None:
        # Dado que existe uma sessão e ocorre uma falha comum de validação
        state = AppState()
        api = Mock()
        state.api = api
        handler = object.__new__(Handler)
        handler.path = "/api/accesses"
        handler.refresh_accesses = Mock(side_effect=ValueError("Falha comum"))
        handler.send_json = Mock()

        # Quando o endpoint trata a falha, então a sessão permanece autenticada
        with patch("tools.studio_sync.web.STATE", state):
            handler.do_POST()

        self.assertIs(api, state.api)
        self.assertTrue(state.public()["authenticated"])

    def test_deve_descartar_sistemas_quando_sessao_expirar_durante_consulta(self) -> None:
        # Dado que uma consulta de sistemas está em andamento quando outra ação expira a sessão
        state = AppState()
        api = Mock()
        state.api = api
        state.accesses = [AccessOption("Entidade", "2", "20", "56", "Contratos")]
        api.list_permitted_systems.side_effect = lambda _access: (
            state.expire_session("Sessão expirada ou acesso não autorizado."),
            [AccessOption("Entidade", "2", "20", "57", "Orquestrador")],
        )[1]
        handler = object.__new__(Handler)
        handler.read_json = Mock(return_value={"entity": "2"})
        handler.send_json = Mock()

        # Quando a resposta atrasada chega, então ela não repopula o estado da sessão encerrada
        with patch("tools.studio_sync.web.STATE", state):
            with self.assertRaises(SessionExpiredError):
                handler.load_systems()

        self.assertIsNone(state.api)
        self.assertEqual([], state.accesses)

    def test_deve_preservar_nova_sessao_quando_resposta_antiga_chegar_atrasada(self) -> None:
        # Dado que uma nova autenticação substitui a API enquanto sistemas antigos são consultados
        state = AppState()
        old_api = Mock()
        new_api = Mock()
        state.api = old_api
        state.accesses = [AccessOption("Entidade", "2", "20", "56", "Contratos")]
        old_api.list_permitted_systems.side_effect = lambda _access: (
            setattr(state, "api", new_api),
            [AccessOption("Entidade", "2", "20", "57", "Orquestrador")],
        )[1]
        handler = object.__new__(Handler)
        handler.read_json = Mock(return_value={"entity": "2"})

        # Quando a resposta antiga chega, então é descartada sem encerrar a sessão nova
        with patch("tools.studio_sync.web.STATE", state):
            with self.assertRaises(StaleOperationError):
                handler.load_systems()

        self.assertIs(new_api, state.api)

    def test_deve_responder_estado_atual_quando_operacao_for_obsoleta(self) -> None:
        # Dado que um endpoint termina com resultado pertencente à sessão anterior
        state = AppState()
        state.api = Mock()
        handler = object.__new__(Handler)
        handler.path = "/api/systems"
        handler.load_systems = Mock(side_effect=StaleOperationError())
        handler.send_json = Mock()

        # Quando o servidor trata a operação obsoleta, então responde a sessão atual sem deslogar
        with patch("tools.studio_sync.web.STATE", state):
            handler.do_POST()

        self.assertTrue(state.public()["authenticated"])
        handler.send_json.assert_called_once_with(state.public())

    def test_deve_ignorar_expiracao_originada_por_sessao_antiga(self) -> None:
        # Dado que uma API antiga responde 401 depois de uma nova autenticação
        state = AppState()
        old_api = Mock()
        new_api = Mock()
        state.api = new_api
        handler = object.__new__(Handler)
        handler.path = "/api/accesses"
        handler.refresh_accesses = Mock(
            side_effect=SessionExpiredError(
                "Sessão expirada ou acesso não autorizado.", source=old_api
            )
        )
        handler.send_json = Mock()

        # Quando o erro atrasado é tratado, então a nova sessão permanece conectada
        with patch("tools.studio_sync.web.STATE", state):
            handler.do_POST()

        self.assertIs(new_api, state.api)
        handler.send_json.assert_called_once_with(state.public())

    def test_interface_and_initial_state_are_consistent(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        state = AppState().public()
        self.assertIn("Desfazer última sincronização", html)
        self.assertIn('id="loading-cancel"', html)
        self.assertIn('id="confirm-eyebrow"', html)
        self.assertIn('src="studio-sync.png"', html)
        self.assertTrue((STATIC / "studio-sync-light.png").is_file())
        self.assertIn('rel="icon"', html)
        self.assertIn("<title>Studio Sync</title>", html)
        self.assertIn('id="theme-toggle"', html)
        self.assertIn("prefers-color-scheme: light", html)
        self.assertIn('class="type-column"', html)
        self.assertIn('id="version-status"', html)
        self.assertIn('id="close">Sair</button>', html)
        self.assertIn("Moises Delfino - Vertical Contratos", html)
        self.assertNotIn('id="close">Encerrar</button>', html)
        self.assertIn('id="refresh-accesses"', html)
        self.assertEqual(html.count('data-step="'), 4)
        self.assertIn('data-panel="1"', html)
        self.assertIn('data-panel="4"', html)
        javascript = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("window.confirm", javascript)
        self.assertIn("CONFIRMAR RESTAURAÇÃO", javascript)
        self.assertIn("function goToStep(step)", javascript)
        self.assertIn("invalidateAnalysis", javascript)
        self.assertIn("kind === 'JOB' ? 'SCRIPT'", javascript)
        self.assertIn("Versão atual", javascript)
        self.assertIn("localStorage.setItem('studio-sync-theme'", javascript)
        self.assertIn("function setTheme(theme)", javascript)
        self.assertIn("studio-sync-light.png", javascript)
        self.assertIn("function closeFolderDialog()", javascript)
        self.assertIn("event.key !== 'Escape'", javascript)
        stylesheet = (STATIC / "styles.css").read_text(encoding="utf-8")
        self.assertIn('html[data-theme="light"]', stylesheet)
        source = (STATIC / "source.js").read_text(encoding="utf-8")
        self.assertIn("/api/accesses", source)
        self.assertIn("!state.authenticated && authenticated", source)
        self.assertIn("await refresh()", source)
        self.assertIn("Atualizar acessos", html)
        self.assertEqual("local", state["versionStatus"])
        self.assertFalse(state["authenticated"])
        self.assertFalse(state["canUndo"])

    def test_operation_can_be_cancelled_and_restarted(self) -> None:
        state = AppState()
        state.begin_operation()
        self.assertFalse(state.cancelled())
        self.assertFalse(state.cancel_operation())
        self.assertFalse(state.public()["busy"])
        state.update("Processando...", True)
        self.assertTrue(state.cancel_operation())
        self.assertTrue(state.cancelled())
        self.assertTrue(state.public()["busy"])
        with self.assertRaisesRegex(RuntimeError, "cancelada"):
            state.ensure_not_cancelled()
        state.begin_operation()
        self.assertFalse(state.cancelled())

    def test_refreshes_accesses_without_reauthentication(self) -> None:
        state = AppState()
        state.api = Mock()
        updated = AccessOption("Entidade nova", "2", "20", "56", "Contratos")
        state.api.list_accesses.return_value = [updated]
        state.summaries = [Mock()]
        state.changes = [Mock()]
        state.duplicate_names = {"duplicado"}
        handler = object.__new__(Handler)
        handler.send_json = Mock()

        with patch("tools.studio_sync.web.STATE", state):
            handler.refresh_accesses()

        self.assertEqual([updated], state.accesses)
        self.assertEqual([], state.summaries)
        self.assertEqual([], state.changes)
        self.assertEqual(set(), state.duplicate_names)
        self.assertFalse(state.busy)
        state.api.list_accesses.assert_called_once_with(quick=True)
        handler.send_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
