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


def atualizar_repositorio(env: dict) -> bool:
    """Atualiza o clone atual sem criar merges nem sobrescrever trabalho local."""
    if not (RAIZ / ".git").exists() or not shutil.which("git"):
        env["STUDIO_SYNC_VERSION_STATUS"] = "local"
        return False
    git_env = dict(env, GIT_TERMINAL_PROMPT="0")
    try:
        resultado = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=RAIZ,
            env=git_env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        env["STUDIO_SYNC_VERSION_STATUS"] = "unavailable"
        print("Não foi possível verificar atualizações. Abrindo a versão local.")
        return False
    if resultado.returncode:
        env["STUDIO_SYNC_VERSION_STATUS"] = "unavailable"
        detalhe = (resultado.stderr or resultado.stdout).strip().splitlines()
        mensagem = detalhe[-1] if detalhe else "falha não identificada"
        print(f"Atualização ignorada ({mensagem}). Abrindo a versão local.")
        return False
    env["STUDIO_SYNC_VERSION_STATUS"] = "current"
    print("Studio Sync atualizado." if "Already up to date" not in resultado.stdout else "Studio Sync já está atualizado.")
    return True


def instalar_integracao_linux() -> None:
    """Mantém o ícone e o atalho do usuário apontando para este inicializador."""
    if not sys.platform.startswith("linux") or not ICONE.exists():
        return
    home = Path.home()
    destino = home / ".local" / "share" / "icons" / "hicolor" / "512x512" / "apps" / "studio-sync.png"
    atalho = home / ".local" / "share" / "applications" / "sincronizador-studio.desktop"
    conteudo_atalho = f"""[Desktop Entry]
Type=Application
Name=Studio Sync
Comment=Sincronize scripts e extensões do Studio Extensões
Exec=/usr/bin/env python3 \"{RAIZ / 'iniciar.py'}\"
Path={RAIZ}
Terminal=false
Icon=studio-sync
Categories=Development;Utility;
StartupNotify=true
"""
    try:
        destino.parent.mkdir(parents=True, exist_ok=True)
        if not destino.exists() or destino.read_bytes() != ICONE.read_bytes():
            shutil.copy2(ICONE, destino)
        atalho.parent.mkdir(parents=True, exist_ok=True)
        if not atalho.exists() or atalho.read_text(encoding="utf-8") != conteudo_atalho:
            atalho.write_text(conteudo_atalho, encoding="utf-8")
            atalho.chmod(0o755)
    except OSError:
        # A integração é visual e não deve impedir a abertura da aplicação.
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
    atualizar_repositorio(env)
    instalar_integracao_linux()
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
