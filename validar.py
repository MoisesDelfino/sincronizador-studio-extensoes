from __future__ import annotations

import shutil
import subprocess
import sys


def run(command: list[str], description: str) -> None:
    print(f"\n==> {description}")
    subprocess.run(command, check=True)


def main() -> int:
    run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tools/studio_sync/tests", "-q"],
        "Testes Python",
    )
    node = shutil.which("node")
    if not node:
        print("\nERRO: Node.js é necessário para validar o JavaScript.", file=sys.stderr)
        return 1
    run([node, "--check", "tools/studio_sync/static/app.js"], "Sintaxe JavaScript")
    git = shutil.which("git")
    if git:
        run([git, "diff", "--check"], "Consistência do diff")
    print("\nValidação concluída com sucesso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
