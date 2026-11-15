# Plano Crescer Seco

App Android do plano de treino, comida e medidas. É uma tela única (`app/src/main/assets/index.html`) aberta dentro de um WebView, funcionando sem internet. Os dados ficam salvos no próprio celular.

## Baixar o APK

Cada envio para a branch `plano-crescer-seco` gera um APK novo em **Releases**. No celular, abra a página do repositório, toque em Releases e baixe `CrescerSeco.apk`.

## Alterar o app

Edite `app/src/main/assets/index.html` e envie para a branch `plano-crescer-seco`. O GitHub Actions compila sozinho (`.github/workflows/apk.yml`).

A chave em `keystore/app.jks` é fixa para que uma versão nova instale por cima da anterior sem apagar os dados.
