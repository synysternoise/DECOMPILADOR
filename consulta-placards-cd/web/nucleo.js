/*
 * Núcleo da consulta de placards CD — sem acesso ao DOM, testável no Node.
 * Espelha placards_cd/importacao.py (importação CSV/TSV) e
 * placards_cd/manifesto.py (validação do manifesto).
 */
(function (raiz) {
  'use strict';

  var CONFIGURACAO_ALVO = 'CD';
  var NUM_FOLHAS = 20;
  var MAX_LINHA_CABECALHO = 15;
  var ABAS_ESCOPO = { PLASTICO: 'PLACARD, KIT PLASTIC', METALICO: 'PLACARD, KIT METALLIC' };
  var ROTULO_KIT = { PLASTICO: 'Plástico', METALICO: 'Metálico' };
  var COL = { A: 0, B: 1, C: 2, D: 3, E: 4, F: 5, G: 6, H: 7, I: 8, J: 9, K: 10, SH1: 11, AF: 31, AG: 32, AH: 33 };
  var NUM_COLUNAS = 34;
  var ERROS_EXCEL = ['#N/A', '#REF!', '#VALUE!', '#DIV/0!', '#NAME?', '#NUM!', '#NULL!', '#SPILL!', '#CALC!'];
  var CODIGOS_DIVERGENCIA = ['QTY_DIF_SOMA', 'TOTAL_DIF_SOMA', 'QTY_DIF_TOTAL'];

  function ehErroExcel(t) { return ERROS_EXCEL.indexOf(t) >= 0; }

  function semAcentos(s) {
    return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '');
  }

  function letraColuna(indice) {
    var n = indice + 1, letras = '';
    while (n) { var r = (n - 1) % 26; letras = String.fromCharCode(65 + r) + letras; n = Math.floor((n - 1) / 26); }
    return letras;
  }

  function normalizarCabecalho(t) {
    if (!t) return '';
    return semAcentos(t).replace(/\s+/g, ' ').trim().toUpperCase();
  }

  /** Chave de busca: sem acento, maiúscula, sem espaços, hífens, pontos, barras e sublinhados. */
  function normalizarBusca(t) {
    if (t === null || t === undefined) return '';
    return semAcentos(t).toUpperCase().replace(/[\s\-_.\/\\‐-―]+/g, '');
  }

  function normalizarTexto(t) {
    if (t === null || t === undefined) return '';
    return semAcentos(t).toUpperCase().replace(/\s+/g, ' ').trim();
  }

  function extrairConfiguracao(h) {
    if (!h) return [null, null];
    var s = String(h).trim().toUpperCase(), base, cfg;
    var barra = s.lastIndexOf('/');
    if (barra >= 0) {
      base = s.slice(0, barra); cfg = s.slice(barra + 1).trim();
      if (!/^[A-Z]{2,3}$/.test(cfg)) return [null, null];
    } else {
      var m = /^(.+?)\s+([A-Z]{2,3})$/.exec(s);
      if (!m) return [null, null];
      base = m[1]; cfg = m[2];
    }
    base = base.replace(/\s+/g, '');
    if (!base) return [null, null];
    return [cfg, base + '/' + cfg];
  }

  function normalizarTopo(t) { return String(t).replace(/\s+/g, '').toUpperCase(); }

  var RE_PROVISORIO = /CDPL\s*X{2,}/i;
  function ehProvisorio(t) { return !!(t && RE_PROVISORIO.test(t)); }

  function numero(t) {
    if (t === null || t === undefined) return null;
    var s = String(t).trim();
    if (!/^[+-]?\d+(?:[.,]\d+)?$/.test(s)) return null;
    return parseFloat(s.replace(',', '.'));
  }

  function fmtNum(v) {
    if (v === null || v === undefined) return '';
    if (Number.isInteger(v)) return String(v);
    return String(Math.round(v * 1e10) / 1e10);
  }

  function iguais(a, b) { return Math.abs(a - b) < 1e-9; }

  // ------------------------------------------------------------- layout

  function ehLinhaCabecalho(t) {
    return normalizarCabecalho(t[COL.D]) === 'POS' && normalizarCabecalho(t[COL.E]).indexOf('ZON') === 0;
  }

  function detectarKit(cab) {
    var c = normalizarCabecalho(cab[COL.C]), h = normalizarCabecalho(cab[COL.H]);
    if (c.indexOf('CDPL') >= 0 && h.indexOf('CONJUNTO') >= 0) return 'PLASTICO';
    if (c.indexOf('PART NUMBER') >= 0 && h.indexOf('MATERIAL') >= 0) return 'METALICO';
    return null;
  }

  function validarLayout(cab, kit) {
    var n = cab.map(normalizarCabecalho), erros = [], avisos = [];
    function msg(col, esperado) {
      return 'Coluna ' + letraColuna(col) + ': esperado ' + esperado + ', encontrado ' + JSON.stringify(cab[col]) + '.';
    }
    function exigir(c, col, e) { if (!c) erros.push(msg(col, e)); }
    function recomendar(c, col, e) { if (!c) avisos.push(msg(col, e)); }
    exigir(n[COL.A].indexOf('PART NUMBER') >= 0 || /\bPN\b/.test(n[COL.A]), COL.A, 'PART NUMBER (PN novo)');
    exigir(n[COL.B].indexOf('E2') >= 0 || n[COL.B].indexOf('REFER') >= 0, COL.B, 'E2 REFERENCIA');
    if (kit === 'PLASTICO') {
      exigir(n[COL.C].indexOf('CDPL') >= 0, COL.C, 'CDPL (REF)');
      exigir(n[COL.H].indexOf('CONJUNTO') >= 0, COL.H, 'CONJUNTO');
    } else {
      exigir(n[COL.C].indexOf('PART NUMBER') >= 0 && n[COL.C].indexOf('CDPL') < 0, COL.C, 'segundo PART NUMBER');
      exigir(n[COL.H].indexOf('MATERIAL') >= 0, COL.H, 'MATERIAL');
    }
    exigir(n[COL.D] === 'POS', COL.D, 'POS');
    exigir(n[COL.E].indexOf('ZON') === 0, COL.E, 'ZONE');
    exigir(n[COL.F].indexOf('QTY') >= 0 || n[COL.F].indexOf('QTD') >= 0, COL.F, 'QTY');
    exigir(n[COL.G].indexOf('FORMATO') >= 0 || n[COL.G].indexOf('DESCRI') >= 0, COL.G, 'FORMATO');
    for (var k = 0; k < NUM_FOLHAS; k++) {
      var col = COL.SH1 + k, m = /^SH\s*0*(\d+)$/.exec(n[col]);
      exigir(!!m && parseInt(m[1], 10) === k + 1, col, 'SH' + (k + 1));
    }
    exigir(n[COL.AF].indexOf('TOTAL') >= 0, COL.AF, 'Total');
    recomendar(n[COL.I].indexOf('ECOD') === 0, COL.I, 'ECODE');
    recomendar(n[COL.J].indexOf('ACTIO') === 0 || n[COL.J].indexOf('ACAO') === 0, COL.J, 'ACTION');
    recomendar(n[COL.K].indexOf('LIBERA') === 0, COL.K, 'LIBERADO');
    recomendar(n[COL.AG].indexOf('CHECK') >= 0, COL.AG, 'Check');
    return { erros: erros, avisos: avisos };
  }

  // ------------------------------------------------------------- registros

  function calcularAvisos(reg, errosColunas, semCache) {
    var avisos = [];
    function add(c, m) { avisos.push({ codigo: c, mensagem: m }); }
    if (!reg.pn_novo) add('SEM_PN_NOVO', 'Sem PN novo (coluna A vazia).');
    if (ehProvisorio(reg.pn_antigo)) add('CDPL_PROVISORIO', 'Referência provisória (CDPLXXX-XX) na coluna C.');
    if (!reg.descricao) add('SEM_DESCRICAO', 'Descrição (coluna G) não informada.');
    errosColunas.forEach(function (e) { add('ERRO_EXCEL', 'Erro do Excel na coluna ' + letraColuna(e[0]) + ': ' + e[1] + '.'); });
    if (!reg.qty) add('QTY_NAO_INFORMADA', 'QTY prevista (coluna F) não informada.');
    else if (reg.qty_numero === null && !ehErroExcel(reg.qty)) add('QTY_NAO_NUMERICA', 'QTY prevista não numérica: "' + reg.qty + '".');
    if (!reg.folhas.some(function (f) { return f.aparece; })) add('SEM_FOLHAS', 'Nenhuma folha (SH1–SH20) com quantidade.');
    reg.folhas.forEach(function (f) {
      if (f.numero === null && !ehErroExcel(f.texto)) add('FOLHA_NAO_NUMERICA', 'Folha ' + f.folha + ': valor não numérico "' + f.texto + '".');
    });
    var qty = reg.qty_numero, soma = reg.soma_folhas, total = reg.total_numero;
    if (qty !== null && soma !== null && !iguais(qty, soma))
      add('QTY_DIF_SOMA', 'QTY prevista (' + fmtNum(qty) + ') difere da soma das folhas (' + fmtNum(soma) + ').');
    if (!reg.total_registrado) add('TOTAL_NAO_INFORMADO', 'Total registrado (coluna AF) não informado.');
    else if (total !== null && soma !== null && !iguais(total, soma))
      add('TOTAL_DIF_SOMA', 'Total registrado (' + fmtNum(total) + ') difere da soma das folhas (' + fmtNum(soma) + ').');
    if (qty !== null && total !== null && !iguais(qty, total))
      add('QTY_DIF_TOTAL', 'QTY prevista (' + fmtNum(qty) + ') difere do Total registrado (' + fmtNum(total) + ').');
    (semCache || []).forEach(function (col) {
      add('FORMULA_SEM_CACHE', 'Coluna ' + letraColuna(col) + ' tem fórmula sem valor calculado salvo; abra e salve a planilha no Excel.');
    });
    return avisos;
  }

  function montarRegistro(kit, aba, linha, t, rotuloC, topoNorm, cfg, errosColunas, semCache) {
    var folhas = [];
    for (var k = 0; k < NUM_FOLHAS; k++) {
      var texto = t[COL.SH1 + k];
      if (texto) {
        var num = numero(texto);
        folhas.push({ folha: k + 1, texto: texto, numero: num,
          aparece: (num !== null && num > 0) || (num === null && !ehErroExcel(texto)) });
      }
    }
    var nums = folhas.filter(function (f) { return f.numero !== null; }).map(function (f) { return f.numero; });
    var reg = {
      id: kit + '-' + linha, kit: kit, aba: aba, linha: linha,
      pn_novo: t[COL.A], ref_e2: t[COL.B], pn_antigo: t[COL.C], rotulo_c: rotuloC,
      pos: t[COL.D], zona: t[COL.E], qty: t[COL.F], descricao: t[COL.G], topo: t[COL.H],
      topo_normalizado: topoNorm, configuracao: cfg,
      ecode: t[COL.I], action: t[COL.J], liberado: t[COL.K], folhas: folhas,
      total_registrado: t[COL.AF], check_qtd: t[COL.AG], observacoes: t[COL.AH],
      qty_numero: numero(t[COL.F]),
      soma_folhas: nums.length ? nums.reduce(function (a, b) { return a + b; }, 0) : null,
      total_numero: numero(t[COL.AF]),
      provisorio: ehProvisorio(t[COL.C])
    };
    reg.avisos = calcularAvisos(reg, errosColunas || [], semCache || []);
    return reg;
  }

  function textosLinha(linha) {
    var t = [];
    for (var k = 0; k < NUM_COLUNAS; k++) {
      var v = linha[k];
      v = (v === undefined || v === null) ? '' : String(v).trim();
      t.push(v === '' ? null : v);
    }
    return t;
  }

  function ErroLayout(mensagem) { this.name = 'ErroLayout'; this.message = mensagem; }
  ErroLayout.prototype = Object.create(Error.prototype);

  /** Importa uma aba (matriz de textos, como num CSV exportado). */
  function importarAba(kit, aba, linhas, semCacheLinhas) {
    var textos = linhas.map(textosLinha);
    var idx = -1;
    for (var i = 0; i < Math.min(MAX_LINHA_CABECALHO, textos.length); i++) { if (ehLinhaCabecalho(textos[i])) { idx = i; break; } }
    if (idx < 0) throw new ErroLayout('Aba "' + aba + '": cabeçalho com POS em D e ZONE em E não encontrado nas ' + MAX_LINHA_CABECALHO + ' primeiras linhas.');
    var cab = textos[idx];
    var lay = validarLayout(cab, kit);
    if (lay.erros.length) throw new ErroLayout('Aba "' + aba + '", linha de cabeçalho ' + (idx + 1) + ': layout não confere.\n- ' + lay.erros.join('\n- '));
    var registros = [], exclusoes = [], vazias = 0;
    for (var r = idx + 1; r < linhas.length; r++) {
      var numLinha = r + 1, t = textos[r];
      var bruta = linhas[r] || [];
      var tudoVazio = bruta.every(function (v) { return v === null || v === undefined || String(v).trim() === ''; });
      if (tudoVazio) { vazias++; continue; }
      var excluir = function (motivo) { exclusoes.push({ aba: aba, linha: numLinha, motivo: motivo, a: t[COL.A], c: t[COL.C], h: t[COL.H] }); };
      if (t.every(function (v) { return v === null; })) { excluir('conteúdo apenas além da coluna AH'); continue; }
      if (ehLinhaCabecalho(t)) { excluir('cabeçalho repetido'); continue; }
      var ext = extrairConfiguracao(t[COL.H]), cfg = ext[0];
      if (!t[COL.H]) { excluir('coluna H vazia (sem configuração)'); continue; }
      if (cfg === null) { excluir('configuração não identificada na coluna H'); continue; }
      if (cfg !== CONFIGURACAO_ALVO) { excluir('configuração ' + cfg + ' na coluna H (fora do escopo ' + CONFIGURACAO_ALVO + ')'); continue; }
      if (!t[COL.A] && !t[COL.C]) { excluir('sem PN novo (A) e sem PN antigo/CDPL (C)'); continue; }
      var errosCol = [];
      t.forEach(function (v, k) { if (v !== null && ehErroExcel(v)) errosCol.push([k, v]); });
      var semCache = semCacheLinhas && semCacheLinhas[r] ? semCacheLinhas[r].filter(function (k) { return k < NUM_COLUNAS; }) : [];
      registros.push(montarRegistro(kit, aba, numLinha, t, cab[COL.C], ext[1], cfg, errosCol, semCache));
    }
    return { kit: kit, aba: aba, linha_cabecalho: idx + 1, avisos_layout: lay.avisos, registros: registros, exclusoes: exclusoes, linhas_vazias: vazias };
  }

  function resumoKit(res) {
    var topos = {}, regs = res.registros;
    regs.forEach(function (r) { topos[r.topo_normalizado] = (topos[r.topo_normalizado] || 0) + 1; });
    function conta(fn) { return regs.filter(fn).length; }
    return {
      aba: res.aba, linha_cabecalho: res.linha_cabecalho, registros: regs.length,
      sem_pn_novo: conta(function (r) { return !r.pn_novo; }),
      sem_descricao: conta(function (r) { return !r.descricao; }),
      provisorios: conta(function (r) { return r.provisorio; }),
      com_divergencia_quantidade: conta(temDivergencia),
      topos: topos, exclusoes: res.exclusoes.length, linhas_vazias: res.linhas_vazias, avisos_layout: res.avisos_layout
    };
  }

  function temDivergencia(r) {
    return r.avisos.some(function (a) { return CODIGOS_DIVERGENCIA.indexOf(a.codigo) >= 0; });
  }

  // ------------------------------------------------------------- CSV/TSV

  function detectarDelimitador(primeiraLinha) {
    var melhor = ',', max = 0;
    ['\t', ';', ','].forEach(function (d) {
      var n = primeiraLinha.split(d).length - 1;
      if (n > max) { max = n; melhor = d; }
    });
    return melhor;
  }

  /** Parser CSV (RFC 4180) com detecção de delimitador (tab, ; ou ,). */
  function lerCSV(texto) {
    if (texto.charCodeAt(0) === 0xFEFF) texto = texto.slice(1);
    var fimPrimeira = texto.search(/\r?\n/);
    var delim = detectarDelimitador(fimPrimeira >= 0 ? texto.slice(0, fimPrimeira) : texto);
    var linhas = [], linha = [], campo = '', aspas = false, i = 0, n = texto.length;
    while (i < n) {
      var ch = texto[i];
      if (aspas) {
        if (ch === '"') {
          if (texto[i + 1] === '"') { campo += '"'; i += 2; continue; }
          aspas = false; i++; continue;
        }
        campo += ch; i++; continue;
      }
      if (ch === '"' && campo === '') { aspas = true; i++; continue; }
      if (ch === delim) { linha.push(campo); campo = ''; i++; continue; }
      if (ch === '\r' && texto[i + 1] === '\n') { i++; continue; }
      if (ch === '\n' || ch === '\r') { linha.push(campo); linhas.push(linha); linha = []; campo = ''; i++; continue; }
      campo += ch; i++;
    }
    if (campo !== '' || linha.length) { linha.push(campo); linhas.push(linha); }
    return linhas;
  }

  /** Importa um CSV/TSV de uma aba; o kit é identificado pelo cabeçalho. */
  function importarCSV(texto, nomeArquivo) {
    var linhas = lerCSV(texto);
    var cab = null;
    for (var i = 0; i < Math.min(MAX_LINHA_CABECALHO, linhas.length); i++) {
      var t = textosLinha(linhas[i]);
      if (ehLinhaCabecalho(t)) { cab = t; break; }
    }
    var kit = cab ? detectarKit(cab) : null;
    if (!kit) throw new ErroLayout(nomeArquivo + ': não foi possível identificar o kit pelo cabeçalho (C=CDPL (REF) e H=CONJUNTO para plástico; C=PART NUMBER e H=MATERIAL para metálico).');
    return importarAba(kit, ABAS_ESCOPO[kit] + ' [CSV ' + nomeArquivo + ']', linhas);
  }

  // ------------------------------------------------------------- busca

  function indexar(registros) {
    return registros.map(function (r) {
      return {
        r: r,
        pnLit: r.pn_novo ? r.pn_novo.toUpperCase().replace(/\s+/g, '') : '',
        cLit: r.pn_antigo ? r.pn_antigo.toUpperCase().replace(/\s+/g, '') : '',
        pn: normalizarBusca(r.pn_novo), c: normalizarBusca(r.pn_antigo), e2: normalizarBusca(r.ref_e2),
        topo: normalizarBusca(r.topo_normalizado), desc: normalizarTexto(r.descricao), descC: normalizarBusca(r.descricao)
      };
    });
  }

  function pontuar(ix, consulta) {
    var lit = consulta.toUpperCase().replace(/\s+/g, '');
    var q = normalizarBusca(consulta);
    if (!q) return null;
    var nomeC = ix.r.kit === 'PLASTICO' ? 'CDPL' : 'PN antigo';
    if (ix.pnLit && ix.pnLit === lit) return { p: 100, motivo: 'PN novo exato' };
    if (ix.cLit && ix.cLit === lit) return { p: 100, motivo: nomeC + ' exato' };
    if (ix.pn && ix.pn === q) return { p: 95, motivo: 'PN novo exato (ignorando hífens/espaços)' };
    if (ix.c && ix.c === q) return { p: 95, motivo: nomeC + ' exato (ignorando hífens/espaços)' };
    if (ix.e2 && ix.e2 === q) return { p: 90, motivo: 'Referência E2 exata' };
    if (ix.topo && ix.topo === q) return { p: 70, motivo: 'Topo' };
    if (q.length >= 3 && ((ix.pn && ix.pn.indexOf(q) === 0) || (ix.c && ix.c.indexOf(q) === 0))) return { p: 60, motivo: 'Início do PN/' + nomeC };
    if (q.length >= 3 && ((ix.pn && ix.pn.indexOf(q) >= 0) || (ix.c && ix.c.indexOf(q) >= 0) || (ix.e2 && ix.e2.indexOf(q) >= 0)))
      return { p: 50, motivo: 'Parte do PN/' + nomeC + '/E2' };
    if (q.length >= 3 && ix.topo && ix.topo.indexOf(q) >= 0) return { p: 30, motivo: 'Parte do topo' };
    var tokens = normalizarTexto(consulta).split(' ').filter(Boolean);
    if (ix.desc && tokens.length && tokens.every(function (tk) { return ix.desc.indexOf(tk) >= 0; })) return { p: 20, motivo: 'Descrição' };
    if (ix.descC && q.length >= 3 && ix.descC.indexOf(q) >= 0) return { p: 20, motivo: 'Descrição' };
    return null;
  }

  function folhaAparece(reg, folha) {
    return reg.folhas.some(function (f) { return f.folha === folha && f.aparece; });
  }

  function passaFiltros(r, f) {
    if (f.kit && r.kit !== f.kit) return false;
    if (f.topo && r.topo_normalizado !== f.topo) return false;
    if (f.folha && !folhaAparece(r, Number(f.folha))) return false;
    if (f.somenteAvisos && !r.avisos.length) return false;
    return true;
  }

  var ORDEM_KIT = { PLASTICO: 0, METALICO: 1 };

  /** Busca com filtros combinados. Correspondências exatas de PN/CDPL primeiro. */
  function buscar(indice, consulta, filtros) {
    filtros = filtros || {};
    var q = (consulta || '').trim(), saida = [];
    indice.forEach(function (ix) {
      if (!passaFiltros(ix.r, filtros)) return;
      if (!q) { saida.push({ registro: ix.r, pontuacao: 0, motivo: '' }); return; }
      var p = pontuar(ix, q);
      if (p) saida.push({ registro: ix.r, pontuacao: p.p, motivo: p.motivo });
    });
    saida.sort(function (a, b) {
      return (b.pontuacao - a.pontuacao) || (ORDEM_KIT[a.registro.kit] - ORDEM_KIT[b.registro.kit]) || (a.registro.linha - b.registro.linha);
    });
    return saida;
  }

  // ------------------------------------------------------------- manifesto

  var FORMATO_MANIFESTO = 'manifesto-desenhos-placards';
  var VERSAO_MANIFESTO = 1;
  var RE_TOPO = /^[A-Z0-9][A-Z0-9-]*\/[A-Z]{2,3}$/;
  var RE_REVISAO = /^[A-Z0-9][A-Z0-9._-]{0,9}$/;

  function ehObjeto(v) { return v !== null && typeof v === 'object' && !Array.isArray(v); }
  function ehInteiro(v) { return typeof v === 'number' && Number.isInteger(v); }

  function urlHttpsValida(u) {
    try { var x = new URL(u); return x.protocol === 'https:' && !!x.hostname; } catch (e) { return false; }
  }

  function validarManifesto(obj, toposBase) {
    var erros = [], avisos = [];
    function erro(c, cam, m) { erros.push({ codigo: c, caminho: cam, mensagem: m }); }
    function aviso(c, cam, m) { avisos.push({ codigo: c, caminho: cam, mensagem: m }); }
    if (!ehObjeto(obj) || obj.formato !== FORMATO_MANIFESTO) {
      erro('FORMATO_INVALIDO', 'formato', 'O arquivo não é um manifesto (' + FORMATO_MANIFESTO + ').');
      return { erros: erros, avisos: avisos, manifesto: null };
    }
    if (obj.versao_formato !== VERSAO_MANIFESTO) {
      erro('FORMATO_INVALIDO', 'versao_formato', 'Versão de formato não suportada: ' + JSON.stringify(obj.versao_formato) + '.');
      return { erros: erros, avisos: avisos, manifesto: null };
    }
    if (!Array.isArray(obj.desenhos)) {
      erro('DESENHOS_AUSENTE', 'desenhos', "Lista 'desenhos' ausente.");
      return { erros: erros, avisos: avisos, manifesto: null };
    }
    var normalizados = [], vistos = {};
    obj.desenhos.forEach(function (d, i) {
      var cam = 'desenhos[' + i + ']';
      if (!ehObjeto(d)) { erro('TIPO_INVALIDO', cam, 'Entrada deve ser um objeto.'); return; }
      var n = {};
      var cfgN = null;
      if (typeof d.configuracao !== 'string' || !d.configuracao.trim()) erro('CAMPO_OBRIGATORIO', cam + '.configuracao', 'Configuração obrigatória.');
      else {
        cfgN = d.configuracao.trim().toUpperCase();
        if (cfgN !== CONFIGURACAO_ALVO) erro('CONFIGURACAO_INVALIDA', cam + '.configuracao', 'Configuração "' + d.configuracao + '" fora do escopo (' + CONFIGURACAO_ALVO + ').');
      }
      n.configuracao = cfgN;
      var topoN = null;
      if (typeof d.topo !== 'string' || !d.topo.trim()) erro('CAMPO_OBRIGATORIO', cam + '.topo', 'Topo obrigatório.');
      else {
        topoN = normalizarTopo(d.topo);
        if (!RE_TOPO.test(topoN)) erro('TOPO_INVALIDO', cam + '.topo', 'Topo inválido: "' + d.topo + '" (esperado ex.: 171-60473-401/CD).');
        else if (cfgN && topoN.split('/').pop() !== cfgN) erro('TOPO_CONFIG_DIVERGENTE', cam + '.topo', 'Topo ' + topoN + ' não corresponde à configuração ' + cfgN + '.');
        else if (toposBase && toposBase.indexOf(topoN) < 0) aviso('TOPO_FORA_DA_BASE', cam + '.topo', 'Topo ' + topoN + ' não aparece na base carregada.');
      }
      n.topo = topoN;
      var revN = null;
      if (typeof d.revisao !== 'string' || !d.revisao.trim()) erro('CAMPO_OBRIGATORIO', cam + '.revisao', 'Revisão obrigatória.');
      else {
        revN = d.revisao.trim().toUpperCase();
        if (!RE_REVISAO.test(revN)) erro('REVISAO_INVALIDA', cam + '.revisao', 'Revisão inválida: "' + d.revisao + '".');
      }
      n.revisao = revN;
      ['ativa', 'vinculo_conferido'].forEach(function (c) {
        var v = d[c] === undefined ? false : d[c];
        if (typeof v !== 'boolean') { erro('TIPO_INVALIDO', cam + '.' + c, c + ' deve ser true/false.'); v = false; }
        n[c] = v;
      });
      ['conferido_por', 'conferido_em', 'observacoes'].forEach(function (c) {
        var v = d[c] === undefined || d[c] === null ? '' : d[c];
        if (typeof v !== 'string') { erro('TIPO_INVALIDO', cam + '.' + c, c + ' deve ser texto.'); v = ''; }
        n[c] = v;
      });
      var o = d.origem;
      if (!ehObjeto(o)) { erro('ORIGEM_INVALIDA', cam + '.origem', 'Origem do PDF obrigatória (local ou url).'); n.origem = null; }
      else if (o.tipo === 'local') {
        var sha = o.sha256 === undefined || o.sha256 === null ? '' : o.sha256;
        if (typeof o.nome_arquivo !== 'string' || !/\.pdf$/.test(o.nome_arquivo.trim().toLowerCase()))
          erro('ORIGEM_INVALIDA', cam + '.origem.nome_arquivo', 'Nome do arquivo PDF obrigatório (.pdf).');
        if (sha !== '' && (typeof sha !== 'string' || !/^[0-9a-f]{64}$/.test(sha.toLowerCase())))
          erro('ORIGEM_INVALIDA', cam + '.origem.sha256', 'sha256 deve ter 64 caracteres hexadecimais.');
        n.origem = { tipo: 'local', nome_arquivo: typeof o.nome_arquivo === 'string' ? o.nome_arquivo.trim() : null,
          sha256: typeof sha === 'string' ? sha.toLowerCase() : '' };
      } else if (o.tipo === 'url') {
        if (typeof o.url !== 'string' || !urlHttpsValida(o.url.trim())) erro('ORIGEM_INVALIDA', cam + '.origem.url', 'URL deve ser HTTPS.');
        n.origem = { tipo: 'url', url: typeof o.url === 'string' ? o.url.trim() : null };
      } else { erro('ORIGEM_INVALIDA', cam + '.origem.tipo', "Tipo de origem deve ser 'local' ou 'url'."); n.origem = null; }
      var total = d.total_paginas === undefined ? null : d.total_paginas;
      if (total !== null && (!ehInteiro(total) || total < 1)) { erro('PAGINA_INVALIDA', cam + '.total_paginas', 'total_paginas deve ser inteiro positivo.'); total = null; }
      n.total_paginas = total;
      var mapa = d.mapa_folhas, mapaN = {};
      if (!ehObjeto(mapa)) erro('CAMPO_OBRIGATORIO', cam + '.mapa_folhas', 'mapa_folhas obrigatório (objeto {folha: página}).');
      else {
        var paginasVistas = {}, chaves = Object.keys(mapa);
        chaves.forEach(function (chave) {
          var camF = cam + '.mapa_folhas[' + chave + ']', pagina = mapa[chave];
          if (!/^\d+$/.test(chave.trim()) || parseInt(chave, 10) < 1 || parseInt(chave, 10) > NUM_FOLHAS) {
            erro('FOLHA_INVALIDA', camF, 'Folha inválida: "' + chave + '" (1 a ' + NUM_FOLHAS + ').'); return;
          }
          var folha = String(parseInt(chave, 10));
          if (Object.prototype.hasOwnProperty.call(mapaN, folha)) { erro('FOLHA_DUPLICADA', camF, 'Folha ' + folha + ' mapeada mais de uma vez.'); return; }
          if (!ehInteiro(pagina) || pagina < 1) { erro('PAGINA_INVALIDA', camF, 'Página inválida para a folha ' + folha + ': ' + JSON.stringify(pagina) + '.'); return; }
          if (n.total_paginas && pagina > n.total_paginas) { erro('PAGINA_INVALIDA', camF, 'Página ' + pagina + ' da folha ' + folha + ' excede o total de ' + n.total_paginas + ' páginas.'); return; }
          if (Object.prototype.hasOwnProperty.call(paginasVistas, pagina)) aviso('PAGINA_REPETIDA', camF, 'Página ' + pagina + ' usada pelas folhas ' + paginasVistas[pagina] + ' e ' + folha + '.');
          else paginasVistas[pagina] = Number(folha);
          mapaN[folha] = pagina;
        });
        if (!chaves.length) aviso('MAPA_VAZIO', cam + '.mapa_folhas', 'Nenhuma folha mapeada.');
      }
      n.mapa_folhas = mapaN;
      if (topoN && revN) {
        var k = topoN + '|' + revN;
        if (Object.prototype.hasOwnProperty.call(vistos, k)) erro('DUPLICADO', cam, 'Topo ' + topoN + ' revisão ' + revN + ' repetido (já em desenhos[' + vistos[k] + ']).');
        else vistos[k] = i;
      }
      normalizados.push(n);
    });
    var porTopo = {};
    normalizados.forEach(function (n) { if (n.topo) (porTopo[n.topo] = porTopo[n.topo] || []).push(n); });
    Object.keys(porTopo).forEach(function (topo) {
      var ativas = porTopo[topo].filter(function (x) { return x.ativa; }).length;
      if (ativas > 1) erro('MULTIPLAS_ATIVAS', topo, 'Topo ' + topo + ' tem ' + ativas + ' revisões ativas; escolha uma.');
      else if (!ativas) aviso('SEM_ATIVA', topo, 'Topo ' + topo + ' não tem revisão ativa.');
    });
    return { erros: erros, avisos: avisos, manifesto: {
      formato: FORMATO_MANIFESTO, versao_formato: VERSAO_MANIFESTO,
      atualizado_em: typeof obj.atualizado_em === 'string' ? obj.atualizado_em : '', desenhos: normalizados } };
  }

  function chaveDesenho(topo, revisao) { return topo + '|' + revisao; }

  function origemAutorizada(url, origens) {
    try { var u = new URL(url); return u.protocol === 'https:' && (origens || []).indexOf(u.origin) >= 0; } catch (e) { return false; }
  }

  /**
   * Situação do desenho 2D para um topo (e folha, opcional).
   * estado: NAO_ASSOCIADO | SEM_REVISAO_ATIVA | LOCAL_NAO_SELECIONADO |
   *         URL_NAO_AUTORIZADA | FOLHA_SEM_PAGINA | OK
   */
  function resolverDesenho(manifesto, topo, folha, arquivosSessao, origens) {
    var lista = manifesto && manifesto.desenhos ? manifesto.desenhos.filter(function (d) { return d.topo === topo; }) : [];
    if (!lista.length) return { estado: 'NAO_ASSOCIADO' };
    var ativa = lista.filter(function (d) { return d.ativa; })[0];
    if (!ativa) return { estado: 'SEM_REVISAO_ATIVA', revisoes: lista.map(function (d) { return d.revisao; }) };
    var pagina = (folha !== null && folha !== undefined) ? ativa.mapa_folhas[String(folha)] : undefined;
    var r = { desenho: ativa, revisao: ativa.revisao, conferido: ativa.vinculo_conferido,
      pagina: pagina === undefined ? null : pagina, folhaMapeada: pagina !== undefined };
    var urlDoc;
    if (ativa.origem && ativa.origem.tipo === 'local') {
      var arq = arquivosSessao && arquivosSessao.get ? arquivosSessao.get(chaveDesenho(topo, ativa.revisao)) : null;
      if (!arq) { r.estado = 'LOCAL_NAO_SELECIONADO'; return r; }
      urlDoc = arq.url;
    } else if (ativa.origem && ativa.origem.tipo === 'url') {
      if (!origemAutorizada(ativa.origem.url, origens)) { r.estado = 'URL_NAO_AUTORIZADA'; return r; }
      urlDoc = ativa.origem.url.split('#')[0];
    } else { r.estado = 'NAO_ASSOCIADO'; return r; }
    r.urlDocumento = urlDoc;
    if (folha !== null && folha !== undefined && !r.folhaMapeada) { r.estado = 'FOLHA_SEM_PAGINA'; return r; }
    r.estado = 'OK';
    r.urlPagina = r.pagina ? urlDoc + '#page=' + r.pagina : null;
    return r;
  }

  // ------------------------------------------------------------- planilha inteira

  function normalizarNomeAba(nome) { return normalizarCabecalho(nome).replace(/[\s,]+/g, ''); }

  function resolverAbas(nomes) {
    var porNorma = {}, encontradas = {}, faltando = [];
    nomes.forEach(function (n) { porNorma[normalizarNomeAba(n)] = n; });
    Object.keys(ABAS_ESCOPO).forEach(function (kit) {
      var esperado = ABAS_ESCOPO[kit];
      if (nomes.indexOf(esperado) >= 0) encontradas[kit] = esperado;
      else if (porNorma[normalizarNomeAba(esperado)]) encontradas[kit] = porNorma[normalizarNomeAba(esperado)];
      else faltando.push(esperado);
    });
    if (faltando.length) throw new ErroLayout('Aba(s) não encontrada(s): ' + faltando.join(', ') + '. Abas do arquivo: ' + nomes.join(', '));
    var usadas = Object.keys(encontradas).map(function (k) { return encontradas[k]; });
    var ignoradas = nomes.filter(function (n) { return usadas.indexOf(n) < 0; })
      .map(function (n) { return { aba: n, motivo: 'fora do escopo (somente PLACARD, KIT PLASTIC/METALLIC)' }; });
    return { abas: encontradas, ignoradas: ignoradas };
  }

  function compararComReferencia(resumo, ref) {
    var dif = [];
    Object.keys((ref && ref.kits) || {}).forEach(function (kit) {
      var esp = ref.kits[kit], obt = resumo[kit];
      if (!obt) { dif.push(kit + ': aba não importada.'); return; }
      ['registros', 'sem_pn_novo'].forEach(function (c) {
        if (esp[c] !== undefined && esp[c] !== obt[c]) dif.push(kit + '.' + c + ': esperado ' + esp[c] + ', obtido ' + obt[c] + '.');
      });
      if (esp.topo !== undefined) {
        var topos = Object.keys(obt.topos || {}).sort();
        if (!(topos.length === 1 && topos[0] === esp.topo))
          dif.push(kit + '.topo: esperado só ' + esp.topo + ', obtido [' + topos.map(function (t) { return "'" + t + "'"; }).join(', ') + '].');
      }
    });
    return dif;
  }

  /**
   * Monta a base a partir de uma planilha aberta (nomes das abas + leitor).
   * lerAba(nome) -> Promise<linhas>, cada linha uma lista de {texto, formulaSemCache}.
   */
  function importarPlanilha(nomesAbas, lerAba, fonte, referencia) {
    var res;
    try { res = resolverAbas(nomesAbas); } catch (e) { return Promise.reject(e); }
    var kits = Object.keys(res.abas);
    return Promise.all(kits.map(function (k) { return lerAba(res.abas[k]); })).then(function (dados) {
      var resultados = kits.map(function (kit, i) {
        var textos = [], semCache = [];
        dados[i].forEach(function (linha, r) {
          var t = [], s = [];
          for (var c = 0; c < linha.length; c++) {
            var cel = linha[c];
            t.push(cel ? cel.texto : null);
            if (cel && cel.formulaSemCache) s.push(c);
          }
          textos.push(t); semCache.push(s);
        });
        return importarAba(kit, res.abas[kit], textos, semCache);
      });
      var resumo = {}, registros = [], exclusoes = [];
      resultados.forEach(function (r) { resumo[r.kit] = resumoKit(r); registros = registros.concat(r.registros); exclusoes = exclusoes.concat(r.exclusoes); });
      var comp = referencia && referencia.kits ? { referencia: 'snapshot conferido', esperado: referencia.kits, diferencas: compararComReferencia(resumo, referencia) } : null;
      return { formato: 'base-placards-cd', versao_formato: 1, configuracao: CONFIGURACAO_ALVO, fonte: fonte,
        gerado_em: new Date().toISOString().slice(0, 19), resumo: resumo, abas_ignoradas: res.ignoradas,
        exclusoes: exclusoes, comparacao_snapshot: comp, registros: registros };
    });
  }

  /** Mesmo escape de placards_cd/construir_html.py:json_para_script. */
  function jsonParaScript(dados) {
    return JSON.stringify(dados).replace(/&/g, '\\u0026').replace(/</g, '\\u003c').replace(/>/g, '\\u003e')
      .replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
  }

  var api = {
    CONFIGURACAO_ALVO: CONFIGURACAO_ALVO, NUM_FOLHAS: NUM_FOLHAS, ABAS_ESCOPO: ABAS_ESCOPO, ROTULO_KIT: ROTULO_KIT,
    FORMATO_MANIFESTO: FORMATO_MANIFESTO, VERSAO_MANIFESTO: VERSAO_MANIFESTO, CODIGOS_DIVERGENCIA: CODIGOS_DIVERGENCIA,
    normalizarBusca: normalizarBusca, normalizarTexto: normalizarTexto, normalizarTopo: normalizarTopo,
    extrairConfiguracao: extrairConfiguracao, ehProvisorio: ehProvisorio, numero: numero, fmtNum: fmtNum,
    validarLayout: validarLayout, detectarKit: detectarKit, importarAba: importarAba, importarCSV: importarCSV,
    lerCSV: lerCSV, resumoKit: resumoKit, temDivergencia: temDivergencia, ErroLayout: ErroLayout,
    indexar: indexar, buscar: buscar, folhaAparece: folhaAparece,
    validarManifesto: validarManifesto, resolverDesenho: resolverDesenho, chaveDesenho: chaveDesenho,
    origemAutorizada: origemAutorizada, urlHttpsValida: urlHttpsValida, letraColuna: letraColuna,
    resolverAbas: resolverAbas, compararComReferencia: compararComReferencia, importarPlanilha: importarPlanilha, jsonParaScript: jsonParaScript
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else raiz.NucleoPlacards = api;
})(this);
