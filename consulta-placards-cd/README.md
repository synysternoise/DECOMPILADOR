# Consulta de Placards CD

Consulta pública dos placards da configuração CD: pesquisa por PN novo, CDPL ou nome, filtro por idioma do título, card com kit (plástico/metálico), POS, zona, topo, folhas com quantidade e botão para abrir o desenho 2D.

Quem consulta só abre um HTML. Quem mantém (o ADM) atualiza a planilha e roda um `.bat`.

## Como fica na pasta compartilhada

```
Placards CD\                      (pasta de rede ou sincronizada pelo OneDrive/Teams)
├─ Consulta de Placards.html      ← todos abrem este
├─ PLANILHA_PLACARD CD.xlsx       ← só o ADM altera
├─ desenhos\                      ← PDFs com o nome do part number (171-50557-021.pdf)
└─ _adm\
   ├─ ATUALIZAR CONSULTA.bat      ← o ADM roda depois de cada mudança
   ├─ config.json
   └─ (código)
```

## Montar a pasta (uma vez, pelo ADM)

1. Copie **o conteúdo** de `pasta-modelo/` para a pasta compartilhada (ex.: `\\servidor\Engenharia\Placards CD\`).
2. Coloque a planilha na raiz da pasta com o nome `PLANILHA_PLACARD CD.xlsx`. Se o nome for outro, ajuste `planilha` em `_adm\config.json`.
3. Coloque os PDFs em `desenhos\`, cada um com o nome do PN novo (`171-50557-021.pdf`). Placard sem PN novo usa o CDPL (`CDPL568-201.pdf`). Subpastas valem.
4. Em `_adm\config.json`, preencha `desenvolvedor` (nome, contato, iniciais): aparece no rodapé da consulta.
5. Dê dois cliques em `_adm\ATUALIZAR CONSULTA.bat`. Ele mostra quantos placards e desenhos encontrou e grava `Consulta de Placards.html`.
6. Restrinja a escrita da pasta ao ADM nas permissões da rede. Os demais só precisam de leitura.

O computador do ADM precisa de Python (o PyCharm já resolve). Na primeira vez, o `.bat` instala o `openpyxl` sozinho. Quem só consulta não precisa de nada além do Edge ou do Chrome.

## Atualizar

Mudou a planilha ou entrou PDF novo? Rode `ATUALIZAR CONSULTA.bat` de novo. O HTML é trocado de uma vez (ninguém pega arquivo pela metade) e o resumo fica em `_adm\relatorio_ultima_publicacao.md`. O resumo traz contagens, comparação com o snapshot conferido (189 / 72 / 60), placards sem desenho, PDFs sem placard, divergências de quantidade e linhas excluídas.

## Compartilhar com outras pessoas

- **Melhor caminho:** mande o link da pasta (ou um atalho para `Consulta de Placards.html`). Os botões de desenho funcionam porque o HTML e a pasta `desenhos` ficam juntos.
- **Pasta do Teams/SharePoint:** funciona quando a pasta está sincronizada no computador (OneDrive → "Sincronizar"). Aberto pelo navegador dentro do SharePoint, o HTML não roda.
- **Mandar só o HTML por e-mail:** a pesquisa funciona, mas os desenhos só abrem se `links_absolutos` estiver `true` no `config.json` (o link passa a apontar para o caminho de rede) e a pessoa tiver acesso à pasta.

## Regras dos dados

- Lê só as abas **PLACARD, KIT PLASTIC** e **PLACARD, KIT METALLIC**, e só as linhas com configuração **CD** na coluna H. LX, AL, placas de saída e abas auxiliares ficam de fora (listadas no relatório).
- A planilha nunca é alterada (o importador confere o SHA-256 antes e depois). Macros não rodam.
- Layout conferido por posição e cabeçalho (A=PART NUMBER, C=CDPL (REF) / 2º PART NUMBER, D=POS, E=ZONE, H=CONJUNTO / MATERIAL, L:AE=SH1…SH20). Se não bater, a publicação para e diz qual coluna está errada.
- Uma linha = um placard; nada é deduplicado nem herdado da linha de cima. POS mantém os zeros (`00122`).
- O idioma vem das siglas no título (ING, FRA/FRAN, ESP, POR, PIC/PICTORIAL…). Só aparecem os idiomas que existem na planilha.

## Para o desenvolvedor

```
pasta-modelo/_adm/placards_cd/   leitura da planilha (leitores.py), regras (importacao.py), publicação (publicar.py)
pasta-modelo/_adm/web/           template.html, estilo.css, aviao.js, busca.js, app.js
testes/                          pytest + node, com planilha e PDFs sintéticos
```

```
pip install openpyxl pytest reportlab playwright && python -m playwright install chromium
python -m pytest testes -q
node --test testes/busca.test.mjs
```
