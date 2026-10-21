"""Prepara o ambiente na primeira execução e abre o Studio Sync.

Usa apenas a biblioteca padrão, para poder rodar antes de qualquer dependência.
"""
import os
import shutil
import subprocess
import sys
import venv
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VENV = RAIZ / ".venv"
NAVEGADORES = RAIZ / ".browsers"
REQUISITOS = RAIZ / "tools" / "studio_sync" / "requirements.txt"
MARCA = RAIZ / ".preparado"
ICONE = RAIZ / "assets" / "studio-sync.png"


LIBS = RAIZ / ".libs"


def instalar_icone_linux() -> None:
    """Registra o ícone no tema do usuário sem exigir acesso administrativo."""
    if not sys.platform.startswith("linux") or not ICONE.exists():
        return
    destino = Path.home() / ".local" / "share" / "icons" / "hicolor" / "512x512" / "apps" / "studio-sync.png"
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        if not destino.exists() or destino.read_bytes() != ICONE.read_bytes():
            shutil.copy2(ICONE, destino)
    except OSError:
        # O ícone é apenas visual e não deve impedir a abertura da aplicação.
        pass


def python_do_venv() -> Path:
    pasta, nome = ("Scripts", "python.exe") if os.name == "nt" else ("bin", "python")
    return VENV / pasta / nome


def criar_venv() -> bool:
    try:
        venv.EnvBuilder(with_pip=True, clear=True).create(VENV)
        return True
    except (subprocess.CalledProcessError, ImportError, SystemExit):
        shutil.rmtree(VENV, ignore_errors=True)
        return False


def preparar(env: dict) -> None:
    print("Preparando o Studio Sync (somente na primeira vez, pode levar alguns minutos)...")
    if criar_venv():
        py = str(python_do_venv())
        subprocess.check_call([py, "-m", "pip", "install", "--disable-pip-version-check", "-r", str(REQUISITOS)])
    else:
        # Sem o módulo venv (comum no Ubuntu/Debian): instala as dependências na pasta do app.
        py = sys.executable
        try:
            subprocess.check_call([py, "-m", "pip", "install", "--disable-pip-version-check",
                                   "--target", str(LIBS), "-r", str(REQUISITOS)])
        except subprocess.CalledProcessError:
            print("Não foi possível instalar as dependências. No Ubuntu/Debian, execute:")
            print("  sudo apt install python3-venv python3-pip")
            raise SystemExit(1)
        env = dict(env, PYTHONPATH=str(LIBS))
    subprocess.check_call([py, "-m", "playwright", "install", "chromium"], env=env)
    MARCA.parent.mkdir(exist_ok=True)
    MARCA.write_text("ok")


def interprete(env: dict):
    if python_do_venv().exists():
        return str(python_do_venv()), env
    return sys.executable, dict(env, PYTHONPATH=str(LIBS))


def main() -> int:
    if sys.version_info < (3, 10):
        print("É necessário Python 3.10 ou mais recente.")
        return 1
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(NAVEGADORES))
    instalar_icone_linux()
    try:
        if not MARCA.exists():
            preparar(env)
        py, env = interprete(env)
        return subprocess.call([py, str(RAIZ / "sincronizar_studio.py")], env=env, cwd=RAIZ)
    except subprocess.CalledProcessError:
        print("Falha na preparação. Verifique a conexão com a internet e tente novamente.")
        return 1


if __name__ == "__main__":
    code = main()
    if code:
        input("Pressione Enter para fechar...")
    sys.exit(code)
