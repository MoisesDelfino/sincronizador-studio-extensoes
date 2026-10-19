from __future__ import annotations

import unittest

from tools.studio_sync.auth import selected_context_from_url


class AuthenticationTests(unittest.TestCase):
    def test_extracts_selected_entity_from_studio_route(self) -> None:
        database, entity = selected_context_from_url(
            "https://scripts.plataforma.betha.cloud/"
            "#/entidades/ZGF0YWJhc2U6NDUyOSxlbnRpdHk6NDc0Ng==/sistemas/151"
        )
        self.assertEqual(("4529", "4746"), (database, entity))

    def test_extracts_selected_entity_from_access_request(self) -> None:
        database, entity = selected_context_from_url(
            "https://plataforma-autorizacoes.betha.cloud/user-accounts/v0.1/api/"
            "suite/users/@me/access/ZGF0YWJhc2U6NDUyOSxlbnRpdHk6NDc0Ng%3D%3D/systems"
        )
        self.assertEqual(("4529", "4746"), (database, entity))


if __name__ == "__main__":
    unittest.main()
