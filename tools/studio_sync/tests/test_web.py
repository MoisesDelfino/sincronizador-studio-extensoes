from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from tools.studio_sync.models import AccessOption
from tools.studio_sync.web import AppState, Handler, STATIC


class WebSmokeTests(unittest.TestCase):
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
