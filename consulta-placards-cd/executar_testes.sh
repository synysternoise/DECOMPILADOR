#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"
python3 -m pytest testes -q -p no:cacheprovider
node --test testes/busca.test.mjs
