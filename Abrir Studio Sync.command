#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then
  echo "Python 3 nao encontrado. Instale em https://www.python.org/downloads/ e abra novamente."
  read -p "Pressione Enter para fechar..."; exit 1
fi
python3 iniciar.py
