from __future__ import annotations

import unittest

from tools.studio_sync.web import AppState, STATIC


class WebSmokeTests(unittest.TestCase):
    def test_interface_and_initial_state_are_consistent(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        state = AppState().public()
        self.assertIn("Desfazer última sincronização", html)
        self.assertIn('id="loading-cancel"', html)
        self.assertIn('id="confirm-eyebrow"', html)
        self.assertIn('src="studio-sync.png"', html)
        self.assertIn('rel="icon"', html)
        self.assertIn('class="type-column"', html)
        self.assertEqual(html.count('data-step="'), 4)
        self.assertIn('data-panel="1"', html)
        self.assertIn('data-panel="4"', html)
        javascript = (STATIC / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("window.confirm", javascript)
        self.assertIn("CONFIRMAR RESTAURAÇÃO", javascript)
        self.assertIn("function goToStep(step)", javascript)
        self.assertIn("invalidateAnalysis", javascript)
        self.assertIn("kind === 'JOB' ? 'SCRIPT'", javascript)
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


if __name__ == "__main__":
    unittest.main()
