# Consulta de placards — configuração CD

Catálogo local para localizar a aplicação de um placard pelo **PN novo** ou pelo **CDPL antigo**. Cada resultado mostra descrição, topo (desenho), POS, zona, folhas e quantidade por folha. Também abre o desenho 2D na página certa quando existe um mapa folha → página cadastrado.

> A consulta é de apoio. **Não substitui o desenho liberado.** A planilha Excel é a fonte de referência e nunca é alterada: o importador só lê o arquivo e confere o SHA-256 antes e depois da leitura.

## Conteúdo

| Caminho | O que é |
|---|---|
| `placards_cd/importar.py` | Importador reproduzível: planilha (ou CSV/TSV) → base JSON + relatório + HTML |
| `placards_cd/leitores.py` | Leitura somente-leitura de `.xlsx`/`.xlsm` (openpyxl), `.xls` (xlrd) e CSV/TSV. Macros nunca são executadas |
| `placards_cd/importacao.py` | Regras dos dados: layout, filtro CD, registros, avisos, exclusões |
| `placards_cd/manifesto.py`, `validar_manifesto.py` | Validação do manifesto de desenhos 2D e conferência dos PDFs |
| `web/` | Modelo do HTML (`template.html`, `estilo.css`, `app.js`, `nucleo.js`, `xlsx.js` — leitor de .xlsx no navegador) |
| `config/snapshot_conferido.json` | Contagens do recorte conferido (189 / 72 / 60), usadas **só para comparação** no relatório |
| `desenhos/manifesto.modelo.json` | Modelo vazio de manifesto (sem páginas: preencher a partir do PDF liberado) |
| `testes/` | Testes com dados **sintéticos** (planilha, PDF e manifesto gerados na hora) |
| `dist/consulta-placards-cd.html` | A consulta **sem base**: abra e carregue a planilha por ela |

## Uso no PC (sem Python)

1. Abra `dist/consulta-placards-cd.html` no Edge ou no Chrome (dois cliques).
2. Clique em **Carregar planilha (.xlsx)…** e escolha a `PLANILHA_PLACARD CD.xlsx`. A planilha é lida no próprio computador: nada é enviado, macros não rodam e o arquivo não é alterado.
3. Confira as contagens que aparecem no topo (e em **Sobre a base**). Se diferirem do snapshot conferido (189 / 72 / 60), a página avisa e não corrige nada.
4. Clique em **Salvar consulta com esta base…**. O navegador baixa um `consulta-placards-cd.html` com a base embutida. Guarde-o numa pasta autorizada: é esse arquivo que você e a equipe abrem no dia a dia, sem carregar a planilha de novo.
5. Quando a planilha mudar, repita os passos 2 e 4.

`.xls` antigo não é lido pela página: abra no Excel e use **Salvar como → Pasta de Trabalho do Excel (.xlsx)**. A página usa os valores que o Excel salvou no arquivo; se alguma fórmula vier sem valor (aviso `FORMULA_SEM_CACHE`), abra a planilha no Excel, salve e carregue de novo.

O importador Python abaixo faz o mesmo (com o mesmo resultado, verificado nos testes) e serve para automatizar ou gerar o relatório em Markdown.

## Requisitos

- Para usar a página: só o Edge ou o Chrome.
- Para o importador por linha de comando (opcional): Python 3.10+ com `openpyxl`. Para `.xls` legado, também `xlrd`; para conferir PDFs, `pypdf`.
- Navegador atual (Edge, Chrome ou Firefox) para abrir o HTML. Funciona offline, direto do disco.
- Somente para os testes: `pytest`, `reportlab`, `playwright` (Chromium) e Node 18+.

```sh
pip install -r requirements.txt
```

## Atualizar a base por linha de comando (opcional)

```sh
python -m placards_cd.importar --planilha "PLANILHA_PLACARD CD.xlsx" --saida dist
```

Com desenhos 2D e uma origem HTTPS corporativa autorizada (opcional):

```sh
python -m placards_cd.importar --planilha "PLANILHA_PLACARD CD.xlsx" --saida dist \
    --manifesto desenhos/manifesto.json \
    --origem-autorizada https://intranet.suaempresa.com.br
```

Arquivos gerados em `dist/`:

- `consulta-placards-cd.html`: a consulta, com a base inteira incorporada. Não carrega CDN, não envia telemetria e não faz chamadas de rede (bloqueado também pela Content-Security-Policy da página).
- `base_placards_cd.json`: os mesmos registros, em JSON.
- `relatorio_importacao.md` / `.json`: contagens por kit, comparação com o snapshot conferido, abas ignoradas, **todas as linhas excluídas com o motivo** e registros com divergência de quantidade.

O importador imprime um resumo. Se as contagens diferirem do snapshot conferido (189 plásticos; 72 metálicos, 60 sem PN novo), ele **reporta a diferença e não altera a importação**. Para comparar com outra referência, use `--referencia arquivo.json`; para não comparar, `--sem-referencia`.

Erros de layout interrompem a geração (código de saída 2) e listam coluna por coluna o que não confere.

### `.xls` legado

O formato é aceito diretamente quando o `xlrd` está instalado. Se não estiver, abra no Excel e use **Salvar como → Pasta de Trabalho do Excel (.xlsx)** sem habilitar macros, e importe o `.xlsx`.

### Fórmulas sem valor salvo

O importador lê os valores calculados que o Excel guarda no arquivo e não recalcula fórmulas. Se uma célula com fórmula vier sem valor (aviso `FORMULA_SEM_CACHE`), abra a planilha no Excel, salve e importe de novo.

### Alternativa: CSV/TSV

Exporte cada aba (**PLACARD, KIT PLASTIC** e **PLACARD, KIT METALLIC**) como CSV (`;` ou `,`) ou texto separado por tabulação, mantendo o cabeçalho e as colunas A:AH nas posições originais. O kit é identificado pelo cabeçalho.

- Pelo importador: `python -m placards_cd.importar --csv plastico.csv --csv metalico.txt --saida dist`
- Pela página: painel **Importar base de CSV/TSV**. A base importada vale só para a sessão, aparece rotulada como "importada de CSV/TSV" e é descartada ao recarregar.

## Regras aplicadas aos dados

- **Escopo:** somente as abas *PLACARD, KIT PLASTIC* e *PLACARD, KIT METALLIC*. As demais abas (placas de saída, Controle de Folhas, auxiliares) são ignoradas e listadas no relatório.
- **Layout validado por posição e cabeçalho:** D=POS, E=ZONE, F=QTY, G=FORMATO, L:AE=SH1…SH20, AF=Total. No plástico, C=CDPL (REF) e H=CONJUNTO. No metálico, C=segundo PART NUMBER e H=MATERIAL. O metálico não é mapeado só pelo nome da coluna.
- **Configuração CD:** lida da coluna H (`171-60473-401/ CD` → topo `171-60473-401/CD`). Linhas LX, AL, com H vazia ou sem configuração reconhecível são excluídas e registradas.
- **Uma linha da fonte = um registro**, com aba e número da linha. Não há deduplicação por PN ou CDPL, e nada é herdado da linha anterior. Linha sem PN novo é mantida quando C está preenchida; sem A e sem C, é excluída.
- **Texto, não número:** identificadores são tratados como texto. Zeros à esquerda de POS são preservados pelo formato da célula (`00000` → `00122`). Célula vazia ≠ zero: um zero numa folha aparece como "0 (zero registrado)" e não conta como presença.
- **Folhas:** SHn é a quantidade na folha n. Todas as folhas preenchidas aparecem. A zona exibida é a da linha (a fonte não detalha zona por folha).
- **Quantidades:** QTY prevista, soma das folhas e Total registrado aparecem separadas. Divergências viram aviso e nada é corrigido. O Check de quantidade (AG) não significa liberação.
- **Avisos por registro:** sem PN novo, CDPLXXX-XX (referência provisória), sem descrição, erro do Excel (#N/A etc.), valor não numérico em folha, fórmula sem valor salvo e divergências de quantidade.

## Operar a consulta

1. Abra `dist/consulta-placards-cd.html` no navegador. O topo mostra o arquivo de origem, a data da importação, as contagens e o SHA-256. Se aparecer **"Base não carregada"**, o HTML foi gerado sem planilha.
2. Digite PN novo, CDPL, referência E2, parte da descrição ou topo. Maiúsculas, espaços e hífens são ignorados (`17150557021` encontra `171-50557-021`), mas os códigos aparecem como estão na fonte. Correspondências exatas de PN/CDPL vêm primeiro, com a etiqueta **exato**.
3. Combine filtros de **kit**, **topo**, **folha** e **somente com avisos**. O filtro de folha não esconde as outras folhas na ficha: a folha filtrada só fica destacada.
4. Teclado: `↓` vai da busca para a lista, `↑`/`↓` navegam, `Enter` abre a ficha e **Voltar aos resultados** devolve o foco.
5. A ficha mostra todos os campos (ausentes aparecem como "não informado"), as três quantidades, a tabela de folhas com o estado do desenho 2D, os avisos e a origem (aba e linha).
6. **Sobre a base** lista contagens, a comparação com o snapshot, abas ignoradas e linhas excluídas.

## Desenhos 2D

### Manifesto (versionado, somente metadados)

```json
{
  "formato": "manifesto-desenhos-placards",
  "versao_formato": 1,
  "atualizado_em": "2026-11-24",
  "desenhos": [{
    "configuracao": "CD",
    "topo": "171-60473-401/CD",
    "revisao": "A",
    "ativa": true,
    "origem": { "tipo": "local", "nome_arquivo": "171-60473-401_A.pdf", "sha256": "…" },
    "total_paginas": 24,
    "mapa_folhas": { "1": 3, "2": 4, "20": 22 },
    "vinculo_conferido": false,
    "conferido_por": "", "conferido_em": "", "observacoes": ""
  }]
}
```

- `mapa_folhas` é explícito: `{folha: página do PDF}`, com páginas começando em 1. **Folha nunca é deduzida da página**, porque capas e índices deslocam a numeração. Folha sem entrada = "sem página mapeada".
- `origem` é `{"tipo": "local", "nome_arquivo", "sha256"}` ou `{"tipo": "url", "url": "https://…"}`. Uma URL só abre se a origem dela foi autorizada com `--origem-autorizada`, e só quando alguém clica. Nenhum link é carregado automaticamente.
- Cada topo pode ter várias revisões, com no máximo uma `ativa`.
- `vinculo_conferido` começa em `false`. Só marque `true` depois de conferir o mapa contra o **PDF liberado**. Enquanto isso, a ficha avisa "Vínculo NÃO conferido".

Validação (topo, configuração, revisão, duplicatas, revisões ativas, folhas 1–20, páginas inteiras ≥ 1 e ≤ total, URL HTTPS, chaves JSON duplicadas) e conferência dos PDFs locais (SHA-256 e número de páginas):

```sh
python -m placards_cd.validar_manifesto desenhos/manifesto.json \
    --base dist/base_placards_cd.json --pasta-pdf "caminho/autorizado/desenhos"
```

### Na página

- A ficha distingue: **PDF não associado**, **PDF local precisa ser selecionado novamente**, **folha sem página mapeada**, **nenhuma revisão ativa** e **URL não autorizada**.
- PDFs locais não ficam guardados na página (por segurança): selecione o arquivo a cada sessão. Se o manifesto tiver SHA-256, um arquivo diferente é recusado. Se não tiver, o hash é preenchido e entra no próximo export.
- **Ver folha N (pág. P)** abre o PDF na página mapeada (`#page=P`). **Abrir documento inteiro** abre o PDF sem posição, com a lista "folha → página" para navegação manual.
- No painel **Desenhos 2D**: escolher a revisão ativa, associar/editar revisões (formulário com as 20 folhas), importar e exportar o manifesto. O export leva só os metadados, nunca o PDF. Manifesto inválido não é aplicado e os erros são listados.
- Textos do Excel e do manifesto são sempre exibidos como texto, nunca interpretados como HTML.

## Testes

```sh
./executar_testes.sh        # pytest (importador, manifesto, interface no Chromium) + node --test (núcleo JS)
```

Todos os dados de teste são **sintéticos**, gerados em pasta temporária: uma planilha com o mesmo layout (189 plásticos; 72 metálicos, 60 sem PN novo; linhas LX/AL; abas de placas de saída) e um PDF de 24 páginas (capa, índice, folhas 1–20 nas páginas 3–22). Cobertura:

- critérios 1–4 (contagens, `171-50557-021`/`CDPL569-1-16` com e sem hífens, `171-60555-001` nas folhas 6/7/9/11, `CDPL568-201` sem PN e sem descrição, divergência da linha 130, fonte inalterada);
- filtros combinados, valores ausentes, zeros à esquerda, aspas, acentos, tentativa de injeção de HTML, dados não CD, layout inválido, `.xls` (convertido pelo LibreOffice) e CSV/TSV;
- paridade entre o importador Python e a página (planilha .xlsx carregada no navegador, inclusive regravada pelo LibreOffice, e CSV/TSV);
- salvar a consulta com a base embutida e reabrir o arquivo salvo;
- PDF: folha 20 → página 22, troca de revisão ativa (→ página 23), mapa ausente (folha 19), documento inteiro, PDF errado recusado pelo SHA-256, URL não autorizada, export/import do manifesto;
- ausência de qualquer requisição de rede durante o uso da página.

## Limitações e pendências

- **Os dados reais ainda não foram carregados**: a planilha não foi fornecida (só fotos da tela). Os critérios 1–4 foram verificados na planilha sintética. Rode o importador no arquivo real e confira o relatório contra o snapshot.
- **Nenhum vínculo oficial folha → página foi validado.** O manifesto em `desenhos/` é só um modelo vazio. Preencha a partir dos PDFs liberados e só então marque `vinculo_conferido`.
- O protótipo `consulta-placards-cd.html` mencionado no pedido não foi recebido. A interface foi feita do zero seguindo os requisitos.
- Abrir na página (`#page=P`) depende do leitor de PDF do navegador (Edge, Chrome e Firefox suportam). Em leitores que ignoram o parâmetro, use "documento inteiro" com a lista de páginas.
- Células mescladas não são "herdadas" (regra do pedido). Linhas que dependam de mesclagem em H aparecem como excluídas no relatório.
- Mantenha a planilha, o HTML gerado, a base JSON e os PDFs em armazenamento autorizado. O `.gitignore` já impede versionar esses arquivos.
