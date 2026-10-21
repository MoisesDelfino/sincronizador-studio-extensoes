from __future__ import annotations

import unittest

from tools.studio_sync.web import AppState, STATIC


class WebSmokeTests(unittest.TestCase):
    def test_interface_and_initial_state_are_consistent(self) -> None:
        html = (STATIC / "index.html").read_text(encoding="utf-8")
        state = AppState().public()
        self.assertIn("Desfazer última sincronização", html)
        self.assertFalse(state["authenticated"])
        self.assertFalse(state["canUndo"])


if __name__ == "__main__":
    unittest.main()
