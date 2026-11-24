#!/usr/bin/env sh
# Roda todos os testes (dados sintéticos). Uso: ./executar_testes.sh
set -e
cd "$(dirname "$0")"
python3 -m pytest testes -q
node --test testes/nucleo.test.mjs
