from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.studio_sync.cache import ArtifactCache
from tools.studio_sync.models import ArtifactKind, RemoteArtifact


class ArtifactCacheTests(unittest.TestCase):
    def test_reuses_source_only_for_same_context_and_revision(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cache = ArtifactCache(Path(directory))
            artifact = RemoteArtifact(ArtifactKind.COMPONENT, "Exemplo", "10", "20", "codigo")
            cache.put("entity-system-a", artifact)

            cached = cache.get(
                "entity-system-a", ArtifactKind.COMPONENT, "Exemplo", "10", "20"
            )
            self.assertIsNotNone(cached)
            self.assertEqual("codigo", cached.source_code if cached else "")
            self.assertIsNone(
                cache.get("entity-system-a", ArtifactKind.COMPONENT, "Exemplo", "10", "21")
            )
            self.assertIsNone(
                cache.get("entity-system-b", ArtifactKind.COMPONENT, "Exemplo", "10", "20")
            )


if __name__ == "__main__":
    unittest.main()
