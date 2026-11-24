/* Interface da consulta de placards CD. Todo texto vindo do Excel ou do
 * manifesto é inserido com textContent — nunca como HTML. */
(function () {
  'use strict';
  var N = window.NucleoPlacards;
  var $ = function (id) { return document.getElementById(id); };

  function lerJSON(id) {
    try { return JSON.parse($(id).textContent); } catch (e) { return null; }
  }

  var config = lerJSON('dados-config') || {};
  var origens = (config.origens_pdf_autorizadas || []).slice();
  var estado = {
    base: null, origemBase: null, indice: [], toposBase: [],
    manifesto: null, manifestoOrigem: null, manifestoAlterado: false,
    arquivos: new Map(), selecionado: null, limite: 100, resultados: [], editando: null, pendentePdf: null
  };

  // ---------------------------------------------------------------- utilidades DOM
  function el(tag, attrs, filhos) {
    var e = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === 'class') e.className = v;
      else if (k === 'texto') e.textContent = v;
      else if (k.indexOf('on') === 0) e.addEventListener(k.slice(2), v);
      else if (v === true) e.setAttribute(k, '');
      else e.setAttribute(k, String(v));
    });
    (filhos || []).forEach(function (f) {
      if (f === null || f === undefined || f === false) return;
      e.appendChild(typeof f === 'string' || typeof f === 'number' ? document.createTextNode(String(f)) : f);
    });
    return e;
  }
  function limpar(no) { while (no.firstChild) no.removeChild(no.firstChild); return no; }
  function valor(v) { return v ? document.createTextNode(v) : el('span', { class: 'nao-inf', texto: 'não informado' }); }
  function rotuloKit(k) { return N.ROTULO_KIT[k] || k; }
  function avisar(msg, tipo) {
    var a = $('aviso-global');
    limpar(a).appendChild(el('div', { class: tipo === 'erro' ? 'erro-caixa' : (tipo === 'ok' ? 'ok-caixa' : 'info-caixa'), texto: msg }));
  }
  function dataHora(iso) { return iso ? String(iso).replace('T', ' ') : '—'; }
  function hoje() { return new Date().toISOString().slice(0, 10); }

  // ---------------------------------------------------------------- base
  function definirBase(base, origem) {
    estado.base = base;
    estado.origemBase = base ? origem : null;
    estado.indice = base ? N.indexar(base.registros) : [];
    var topos = {};
    (base ? base.registros : []).forEach(function (r) { topos[r.topo_normalizado] = true; });
    estado.toposBase = Object.keys(topos).sort();
    estado.selecionado = null;
    preencherFiltros();
    renderEstadoBase();
    renderFonte();
    executarBusca();
    renderFicha();
    renderDesenhos();
  }

  function renderEstadoBase() {
    var caixa = limpar($('estado-base')), b = estado.base;
    if (!b) {
      caixa.className = 'estado-base nao-carregada';
      caixa.textContent = 'Base não carregada — este arquivo não contém dados de placards. Gere o HTML com o importador a partir da planilha (veja o README) ou importe CSV/TSV no painel abaixo.';
      $('busca').disabled = true;
      return;
    }
    $('busca').disabled = false;
    var partes = [];
    ['PLASTICO', 'METALICO'].forEach(function (k) {
      if (b.resumo[k]) partes.push(b.resumo[k].registros + ' registros ' + (k === 'PLASTICO' ? 'plásticos' : 'metálicos'));
      else partes.push('kit ' + rotuloKit(k).toLowerCase() + ' NÃO carregado');
    });
    if (estado.origemBase === 'csv') {
      caixa.className = 'estado-base csv';
      caixa.appendChild(document.createTextNode('Base importada de CSV/TSV nesta sessão (' + b.fonte.arquivo + ') — não é a planilha de referência; recarregue a página para voltar à base incorporada. ' + partes.join(' · ') + '.'));
    } else {
      caixa.className = 'estado-base carregada';
      caixa.appendChild(document.createTextNode('Base: ' + b.fonte.arquivo + ' · importada em ' + dataHora(b.gerado_em) + ' · ' + partes.join(' · ') + ' · SHA-256 ' + String(b.fonte.sha256 || '').slice(0, 12) + '…'));
    }
    var comp = b.comparacao_snapshot;
    if (comp && comp.diferencas && comp.diferencas.length) {
      caixa.appendChild(el('div', { texto: 'Atenção: ' + comp.diferencas.length + ' diferença(s) em relação ao snapshot conferido — ver "Sobre a base".' }));
    }
  }

  function preencherFiltros() {
    var ft = $('f-topo'), ff = $('f-folha');
    var topoAtual = ft.value, folhaAtual = ff.value;
    limpar(ft).appendChild(el('option', { value: '', texto: 'Todos' }));
    estado.toposBase.forEach(function (t) { ft.appendChild(el('option', { value: t, texto: t })); });
    ft.value = estado.toposBase.indexOf(topoAtual) >= 0 ? topoAtual : '';
    limpar(ff).appendChild(el('option', { value: '', texto: 'Todas' }));
    var regs = estado.base ? estado.base.registros : [];
    for (var n = 1; n <= N.NUM_FOLHAS; n++) {
      var c = regs.filter(function (r) { return N.folhaAparece(r, n); }).length;
      ff.appendChild(el('option', { value: String(n), texto: 'Folha ' + n + ' (' + c + ')' }));
    }
    ff.value = folhaAtual;
  }

  // ---------------------------------------------------------------- busca
  function filtrosAtuais() {
    return { kit: $('f-kit').value, topo: $('f-topo').value, folha: $('f-folha').value, somenteAvisos: $('f-avisos').checked };
  }

  function descreverFiltros(f) {
    var p = [];
    if (f.kit) p.push('kit ' + rotuloKit(f.kit));
    if (f.topo) p.push('topo ' + f.topo);
    if (f.folha) p.push('folha ' + f.folha);
    if (f.somenteAvisos) p.push('somente com avisos');
    return p.join(', ');
  }

  function executarBusca(manterLimite) {
    if (!manterLimite) estado.limite = 100;
    var q = $('busca').value, f = filtrosAtuais();
    estado.resultados = N.buscar(estado.indice, q, f);
    renderResultados(q, f);
    var exatos = estado.resultados.filter(function (x) { return x.pontuacao >= 95; });
    var unico = exatos.length === 1 ? exatos[0] : (q.trim() && estado.resultados.length === 1 ? estado.resultados[0] : null);
    if (unico && unico.registro.id !== estado.selecionado) abrirFicha(unico.registro.id, false);
  }

  function atualizarRotuloFiltros(f) {
    var n = (f.kit ? 1 : 0) + (f.topo ? 1 : 0) + (f.folha ? 1 : 0) + (f.somenteAvisos ? 1 : 0), r = $('filtros-ativos');
    r.hidden = !n;
    r.textContent = n + ' ativo' + (n > 1 ? 's' : '');
  }

  function renderResultados(q, f) {
    var lista = limpar($('lista')), cont = $('contagem'), res = estado.resultados;
    var desc = descreverFiltros(f);
    if (!estado.base) { cont.textContent = 'Nenhuma base carregada.'; $('mais').hidden = true; return; }
    atualizarRotuloFiltros(f);
    if (!q.trim() && !desc) {
      cont.textContent = 'Digite um PN novo ou CDPL para começar. Base com ' + estado.base.registros.length + ' registros.';
      $('mais').hidden = true;
      return;
    }
    if (!res.length) {
      cont.textContent = 'Nenhum registro encontrado' + (q.trim() ? ' para “' + q.trim() + '”' : '') + (desc ? ' com os filtros: ' + desc : '') + '.';
      lista.appendChild(el('li', {}, [el('p', { class: 'vazio', texto: 'Sem resultados. Verifique o código ou limpe os filtros.' }),
        el('button', { type: 'button', texto: 'Limpar busca e filtros', onclick: limparTudo })]));
      $('mais').hidden = true;
      return;
    }
    var exatos = res.filter(function (x) { return x.pontuacao >= 95; }).length;
    cont.textContent = res.length + ' registro' + (res.length > 1 ? 's' : '') + (exatos ? ' (' + exatos + ' correspondência' + (exatos > 1 ? 's' : '') + ' exata' + (exatos > 1 ? 's' : '') + ')' : '') + (desc ? ' · filtros: ' + desc : '');
    res.slice(0, estado.limite).forEach(function (x) {
      var r = x.registro;
      var l1 = el('span', { class: 'l1' }, [
        el('span', { class: 'etiqueta ' + r.kit.toLowerCase(), texto: rotuloKit(r.kit) }),
        r.pn_novo ? el('span', { class: 'mono', texto: r.pn_novo }) : el('span', { class: 'nao-inf', texto: 'sem PN novo' }),
        r.pn_antigo ? el('span', { class: 'mono', texto: '· ' + r.pn_antigo }) : null,
        x.pontuacao >= 95 ? el('span', { class: 'etiqueta exato', texto: 'exato' }) : null,
        r.avisos.length ? el('span', { class: 'etiqueta aviso', texto: r.avisos.length + ' aviso' + (r.avisos.length > 1 ? 's' : '') }) : null
      ]);
      var folhas = r.folhas.filter(function (fl) { return fl.aparece; }).map(function (fl) { return fl.folha; });
      var l2 = el('span', { class: 'l2 d-block', texto: 'POS ' + (r.pos || '—') + ' · Zona ' + (r.zona || '—') + ' · ' + (r.topo_normalizado || '') + ' · Folhas: ' + (folhas.length ? folhas.join(', ') : '—') });
      var l3 = el('span', { class: 'l3 d-block', texto: r.descricao || 'sem descrição' });
      var botao = el('button', { type: 'button', class: 'item', 'data-id': r.id, 'aria-current': estado.selecionado === r.id ? 'true' : null,
        onclick: function () { abrirFicha(r.id, true); } }, [l1, l2, l3]);
      lista.appendChild(el('li', {}, [botao]));
    });
    $('mais').hidden = res.length <= estado.limite;
    if (!$('mais').hidden) $('mais').textContent = 'Mostrar mais (' + (res.length - estado.limite) + ' restantes)';
  }

  function limparTudo() {
    $('busca').value = ''; $('f-kit').value = ''; $('f-topo').value = ''; $('f-folha').value = ''; $('f-avisos').checked = false;
    executarBusca(); $('busca').focus();
  }

  function registroPorId(id) {
    if (!estado.base) return null;
    for (var i = 0; i < estado.base.registros.length; i++) if (estado.base.registros[i].id === id) return estado.base.registros[i];
    return null;
  }

  // ---------------------------------------------------------------- ficha
  function abrirFicha(id, focar) {
    estado.selecionado = id;
    Array.prototype.forEach.call(document.querySelectorAll('#lista .item'), function (b) {
      if (b.getAttribute('data-id') === id) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
    });
    renderFicha();
    if (focar) { var h = $('ficha-titulo'); if (h) { h.focus({ preventScroll: true }); $('ficha').scrollIntoView({ block: 'start' }); } }
  }

  function divergente(r, codigos) { return r.avisos.some(function (a) { return codigos.indexOf(a.codigo) >= 0; }); }

  function renderFicha() {
    var corpo = limpar($('ficha-corpo')), r = registroPorId(estado.selecionado);
    if (!r) { corpo.appendChild(el('p', { class: 'vazio', texto: estado.base ? 'Selecione um resultado para ver a ficha.' : 'Nenhuma base carregada.' })); return; }
    var folhaFiltro = Number($('f-folha').value) || null;
    corpo.appendChild(el('div', { class: 'acoes' }, [el('button', { type: 'button', texto: '← Voltar aos resultados', onclick: function () {
      var b = document.querySelector('#lista .item[data-id="' + CSS.escape(r.id) + '"]'); (b || $('busca')).focus(); } })]));
    corpo.appendChild(el('h3', { id: 'ficha-titulo', tabindex: '-1' }, [r.pn_novo || r.pn_antigo || '(sem identificador)']));
    corpo.appendChild(el('div', { class: 'acoes' }, [
      el('span', { class: 'etiqueta ' + r.kit.toLowerCase(), texto: 'Kit ' + rotuloKit(r.kit) }),
      r.provisorio ? el('span', { class: 'etiqueta aviso', texto: 'Referência provisória' }) : null,
      el('span', { class: 'etiqueta', texto: 'Configuração ' + r.configuracao })
    ]));
    var presentes = r.folhas.filter(function (f) { return f.aparece; });
    corpo.appendChild(el('div', { class: 'resumo', 'aria-label': 'Onde aplicar' }, [
      el('div', {}, [el('span', { class: 'rot', texto: 'Topo' }), el('b', { texto: r.topo_normalizado })]),
      el('div', {}, [el('span', { class: 'rot', texto: 'POS' }), r.pos ? el('b', { texto: r.pos }) : valor(null)]),
      el('div', {}, [el('span', { class: 'rot', texto: 'Zona' }), r.zona ? el('b', { texto: r.zona }) : valor(null)]),
      el('div', { class: 'larga' }, [el('span', { class: 'rot', texto: 'Folhas (quantidade)' }),
        presentes.length ? el('b', { texto: presentes.map(function (f) { return 'SH' + f.folha + ': ' + f.texto; }).join(' · ') }) : valor(null)])]));
    if (r.avisos.length) {
      corpo.appendChild(el('div', { class: 'avisos', role: 'note', 'aria-label': 'Avisos' }, [
        el('strong', { texto: 'Avisos da fonte (nada foi corrigido):' }),
        el('ul', {}, r.avisos.map(function (a) { return el('li', { texto: a.mensagem }); }))]));
    }
    var dQS = divergente(r, ['QTY_DIF_SOMA', 'QTY_DIF_TOTAL']), dTS = divergente(r, ['TOTAL_DIF_SOMA', 'QTY_DIF_TOTAL']);
    var dSoma = divergente(r, ['QTY_DIF_SOMA', 'TOTAL_DIF_SOMA']);
    function caixaQtd(rot, v, div) {
      return el('div', { class: 'qtd' + (div ? ' divergente' : '') }, [el('span', { class: 'rot', texto: rot }),
        v === null || v === undefined || v === '' ? el('span', { class: 'val nao-inf', texto: 'não informado' }) : el('span', { class: 'val', texto: String(v) })]);
    }
    corpo.appendChild(el('h4', { texto: 'Quantidades (exibidas separadamente)' }));
    corpo.appendChild(el('div', { class: 'qtds' }, [
      caixaQtd('QTY prevista (F)', r.qty, dQS),
      caixaQtd('Soma das folhas (SH1–SH20)', r.soma_folhas === null ? null : N.fmtNum(r.soma_folhas), dSoma),
      caixaQtd('Total registrado (AF)', r.total_registrado, dTS)]));
    var campos = [
      ['PN novo (A)', r.pn_novo], ['Referência E2 (B)', r.ref_e2], [(r.rotulo_c || 'PN antigo') + ' (C)', r.pn_antigo],
      ['Descrição — FORMATO (G)', r.descricao], ['Topo / desenho (H)', r.topo], ['Topo normalizado', r.topo_normalizado],
      ['POS (D)', r.pos], ['Zona da linha (E)', r.zona], ['ECODE (I)', r.ecode], ['ACTION (J)', r.action], ['LIBERADO (K)', r.liberado],
      ['Check de quantidade (AG)', r.check_qtd], ['Observações (AH)', r.observacoes]];
    var dl = el('dl', { class: 'campos' });
    campos.forEach(function (c) { dl.appendChild(el('dt', { texto: c[0] })); dl.appendChild(el('dd', {}, [valor(c[1])])); });
    corpo.appendChild(dl);
    corpo.appendChild(el('p', { class: 'dica', texto: 'O Check de quantidade (AG) é um controle da planilha e não significa liberação.' }));

    // Folhas
    corpo.appendChild(el('h4', { texto: 'Folhas onde o placard aparece' }));
    if (!r.folhas.length) corpo.appendChild(el('p', { class: 'nao-inf', texto: 'Nenhuma folha preenchida (SH1–SH20 vazias).' }));
    else {
      var tb = el('tbody');
      r.folhas.forEach(function (f) {
        var qtdTxt = f.numero === 0 ? '0 (zero registrado)' : f.texto;
        tb.appendChild(el('tr', { class: folhaFiltro === f.folha ? 'filtrada' : null }, [
          el('th', { scope: 'row', texto: 'Folha ' + f.folha + (folhaFiltro === f.folha ? ' (filtrada)' : '') }),
          el('td', { texto: qtdTxt }), el('td', {}, [valor(r.zona)]), el('td', {}, [celulaDesenho(r, f.folha)])]));
      });
      corpo.appendChild(el('table', {}, [
        el('caption', { texto: 'A fonte informa somente a zona da linha (coluna E); a zona não é detalhada por folha.' }),
        el('thead', {}, [el('tr', {}, [el('th', { scope: 'col', texto: 'Folha' }), el('th', { scope: 'col', texto: 'Quantidade' }),
          el('th', { scope: 'col', texto: 'Zona (da linha)' }), el('th', { scope: 'col', texto: 'Desenho 2D' })])]), tb]));
    }
    corpo.appendChild(blocoDesenho(r));
    var fonte = estado.base.fonte || {};
    corpo.appendChild(el('h4', { texto: 'Origem do registro' }));
    corpo.appendChild(el('p', { texto: 'Aba “' + r.aba + '”, linha ' + r.linha + ' — arquivo ' + (fonte.arquivo || '?') +
      (estado.origemBase === 'csv' ? ' (CSV/TSV importado nesta sessão)' : ' (importado em ' + dataHora(estado.base.gerado_em) + ')') + '.' }));
  }

  function textoEstado(s, folha) {
    switch (s.estado) {
      case 'NAO_ASSOCIADO': return ['PDF não associado', 'ruim'];
      case 'SEM_REVISAO_ATIVA': return ['Nenhuma revisão ativa', 'atencao'];
      case 'LOCAL_NAO_SELECIONADO': return ['PDF local precisa ser selecionado novamente' + (s.folhaMapeada ? ' (folha ' + folha + ' → página ' + s.pagina + ')' : (folha ? '; folha ' + folha + ' sem página mapeada' : '')), 'atencao'];
      case 'URL_NAO_AUTORIZADA': return ['URL do PDF não autorizada', 'ruim'];
      case 'FOLHA_SEM_PAGINA': return ['Folha ' + folha + ' sem página mapeada (rev. ' + s.revisao + ')', 'atencao'];
      default: return ['Rev. ' + s.revisao + ': folha ' + folha + ' → página ' + s.pagina, ''];
    }
  }

  function celulaDesenho(r, folha) {
    var s = N.resolverDesenho(estado.manifesto, r.topo_normalizado, folha, estado.arquivos, origens);
    var t = textoEstado(s, folha);
    var filhos = [el('span', { class: 'estado-desenho d-block ' + t[1], texto: t[0] })];
    if (s.estado === 'OK') {
      if (s.desenho.origem.tipo === 'local') filhos.push(el('button', { type: 'button', texto: 'Ver folha ' + folha + ' (pág. ' + s.pagina + ')',
        onclick: function () { abrirVisualizador(s.urlPagina, 'Topo ' + r.topo_normalizado + ' rev. ' + s.revisao + ' — folha ' + folha + ' → página ' + s.pagina + ' do PDF'); } }));
      else filhos.push(el('a', { class: 'botao', href: s.urlPagina, target: '_blank', rel: 'noopener noreferrer', texto: 'Abrir folha ' + folha + ' (pág. ' + s.pagina + ') ↗' }));
    } else if (s.estado === 'LOCAL_NAO_SELECIONADO') {
      filhos.push(el('button', { type: 'button', texto: 'Selecionar PDF…', onclick: function () { pedirPdf(s.desenho); } }));
    } else if (s.estado === 'FOLHA_SEM_PAGINA') {
      filhos.push(botaoDocumentoInteiro(s, 'Documento inteiro'));
    }
    return el('div', {}, filhos);
  }

  function botaoDocumentoInteiro(s, rotulo) {
    if (s.desenho.origem.tipo === 'local') return el('button', { type: 'button', texto: rotulo,
      onclick: function () { abrirVisualizador(s.urlDocumento, 'Topo ' + s.desenho.topo + ' rev. ' + s.revisao + ' — documento inteiro; navegue manualmente pelas páginas.'); } });
    return el('a', { class: 'botao', href: s.urlDocumento, target: '_blank', rel: 'noopener noreferrer', texto: rotulo + ' ↗' });
  }

  function blocoDesenho(r) {
    var caixa = el('div', {}, [el('h4', { texto: 'Desenho 2D do topo ' + r.topo_normalizado })]);
    var s = N.resolverDesenho(estado.manifesto, r.topo_normalizado, null, estado.arquivos, origens);
    var abrirPainel = el('button', { type: 'button', texto: 'Abrir painel de desenhos', onclick: function () { $('painel-desenhos').open = true; $('painel-desenhos').scrollIntoView(); } });
    if (s.estado === 'NAO_ASSOCIADO') {
      caixa.appendChild(el('p', { class: 'estado-desenho ruim', texto: 'PDF não associado: o manifesto não tem desenho para este topo. A lista de peças não substitui o desenho 2D.' }));
      caixa.appendChild(abrirPainel); return caixa;
    }
    if (s.estado === 'SEM_REVISAO_ATIVA') {
      caixa.appendChild(el('p', { class: 'estado-desenho atencao', texto: 'Há revisões cadastradas (' + s.revisoes.join(', ') + '), mas nenhuma está ativa. Escolha a revisão ativa no painel de desenhos.' }));
      caixa.appendChild(abrirPainel); return caixa;
    }
    var d = s.desenho;
    var origemTxt = d.origem.tipo === 'local' ? 'PDF local “' + d.origem.nome_arquivo + '”' : 'URL ' + d.origem.url;
    caixa.appendChild(el('p', { texto: 'Revisão ativa ' + d.revisao + ' · ' + origemTxt + '.' }));
    if (!d.vinculo_conferido) caixa.appendChild(el('p', { class: 'estado-desenho atencao', texto: 'Vínculo folha → página NÃO conferido contra o PDF liberado. Confirme visualmente antes de usar.' }));
    else caixa.appendChild(el('p', { class: 'estado-desenho', texto: 'Vínculo conferido' + (d.conferido_por ? ' por ' + d.conferido_por : '') + (d.conferido_em ? ' em ' + d.conferido_em : '') + '.' }));
    if (s.estado === 'LOCAL_NAO_SELECIONADO') {
      caixa.appendChild(el('p', { class: 'estado-desenho atencao', texto: 'PDFs locais não ficam guardados na página: selecione “' + d.origem.nome_arquivo + '” novamente nesta sessão.' }));
      caixa.appendChild(el('div', { class: 'acoes' }, [el('button', { type: 'button', class: 'primario', texto: 'Selecionar PDF…', onclick: function () { pedirPdf(d); } }), abrirPainel]));
    } else if (s.estado === 'URL_NAO_AUTORIZADA') {
      caixa.appendChild(el('p', { class: 'estado-desenho ruim', texto: 'A URL não pertence a uma origem HTTPS autorizada (' + (origens.join(', ') || 'nenhuma configurada') + '). Nada foi carregado.' }));
    } else {
      caixa.appendChild(el('div', { class: 'acoes' }, [botaoDocumentoInteiro(s, 'Abrir documento inteiro'), abrirPainel]));
    }
    var orient = r.folhas.filter(function (f) { return f.aparece; }).map(function (f) {
      var p = d.mapa_folhas[String(f.folha)];
      return el('li', { texto: 'Folha ' + f.folha + ' → ' + (p ? 'página ' + p + ' do PDF' : 'sem página mapeada') });
    });
    if (orient.length) {
      caixa.appendChild(el('p', { class: 'dica', texto: 'Para navegar manualmente no documento inteiro (capas e índices podem deslocar a numeração; folha ≠ página):' }));
      caixa.appendChild(el('ul', {}, orient));
    }
    return caixa;
  }

  // ---------------------------------------------------------------- visualizador
  function abrirVisualizador(url, info) {
    var sec = $('visualizador'), quadro = limpar($('vis-quadro'));
    // Novo iframe a cada abertura: trocar só o #page de um iframe existente não navega o leitor de PDF.
    quadro.appendChild(el('iframe', { src: url, title: info }));
    $('vis-info').textContent = info;
    $('vis-nova-aba').setAttribute('href', url);
    sec.hidden = false;
    sec.scrollIntoView();
    $('t-vis').setAttribute('tabindex', '-1'); $('t-vis').focus();
  }
  function fecharVisualizador() { limpar($('vis-quadro')); $('visualizador').hidden = true; }

  // ---------------------------------------------------------------- PDF local
  function pedirPdf(desenho) {
    estado.pendentePdf = { topo: desenho.topo, revisao: desenho.revisao };
    var s = $('seletor-pdf'); s.value = ''; s.click();
  }

  function hexDe(buf) { return Array.prototype.map.call(new Uint8Array(buf), function (b) { return ('0' + b.toString(16)).slice(-2); }).join(''); }

  function aoSelecionarPdf(ev) {
    var arq = ev.target.files && ev.target.files[0], alvo = estado.pendentePdf;
    estado.pendentePdf = null;
    if (!arq || !alvo) return;
    var d = encontrarDesenho(alvo.topo, alvo.revisao);
    if (!d) return;
    arq.arrayBuffer().then(function (buf) {
      var cab = String.fromCharCode.apply(null, new Uint8Array(buf.slice(0, 5)));
      if (cab !== '%PDF-') { avisar('“' + arq.name + '” não é um PDF. Nada foi associado.', 'erro'); return null; }
      if (window.crypto && crypto.subtle && crypto.subtle.digest) return crypto.subtle.digest('SHA-256', buf).then(hexDe);
      return '';
    }).then(function (sha) {
      if (sha === null || sha === undefined) return;
      var msgs = [];
      if (d.origem.sha256 && sha && sha !== d.origem.sha256) {
        avisar('“' + arq.name + '” é diferente do PDF registrado no manifesto (SHA-256 não confere). Nada foi associado.', 'erro'); return;
      }
      if (d.origem.sha256 && !sha) msgs.push('Não foi possível conferir o SHA-256 neste navegador.');
      if (arq.name !== d.origem.nome_arquivo) msgs.push('Nome do arquivo (“' + arq.name + '”) difere do manifesto (“' + d.origem.nome_arquivo + '”).');
      if (!d.origem.sha256 && sha) { d.origem.sha256 = sha; estado.manifestoAlterado = true; msgs.push('SHA-256 registrado no manifesto (exporte para guardar).'); }
      var chave = N.chaveDesenho(d.topo, d.revisao), antigo = estado.arquivos.get(chave);
      if (antigo) URL.revokeObjectURL(antigo.url);
      estado.arquivos.set(chave, { url: URL.createObjectURL(arq), nome: arq.name, sha256: sha, tamanho: arq.size });
      avisar('PDF associado nesta sessão a ' + d.topo + ' rev. ' + d.revisao + '. ' + msgs.join(' '), 'ok');
      renderFicha(); renderDesenhos();
    }).catch(function (e) { avisar('Falha ao ler o PDF: ' + e.message, 'erro'); });
  }

  function encontrarDesenho(topo, rev) {
    if (!estado.manifesto) return null;
    return estado.manifesto.desenhos.filter(function (d) { return d.topo === topo && d.revisao === rev; })[0] || null;
  }

  // ---------------------------------------------------------------- manifesto
  function aplicarManifesto(obj, origem) {
    var res = N.validarManifesto(obj, estado.base ? estado.toposBase : null);
    if (res.erros.length) return res;
    estado.manifesto = res.manifesto;
    estado.manifestoOrigem = origem;
    // Mantém PDFs da sessão só se a entrada local continuar com o mesmo arquivo.
    estado.arquivos.forEach(function (v, chave) {
      var p = chave.split('|'), d = encontrarDesenho(p[0], p[1]);
      if (!d || d.origem.tipo !== 'local' || (d.origem.sha256 && v.sha256 && d.origem.sha256 !== v.sha256)) {
        URL.revokeObjectURL(v.url); estado.arquivos.delete(chave);
      }
    });
    return res;
  }

  function listaMensagens(res) {
    var caixa = el('div');
    if (res.erros.length) caixa.appendChild(el('div', { class: 'erro-caixa', role: 'alert' }, [el('strong', { texto: 'Manifesto não aplicado — corrija:' }),
      el('ul', {}, res.erros.map(function (e) { return el('li', { texto: e.caminho + ': ' + e.mensagem }); }))]));
    if (res.avisos.length) caixa.appendChild(el('div', { class: 'avisos' }, [el('strong', { texto: 'Avisos:' }),
      el('ul', {}, res.avisos.map(function (e) { return el('li', { texto: e.caminho + ': ' + e.mensagem }); }))]));
    return caixa;
  }

  function exportarManifesto() {
    var m = estado.manifesto || { formato: N.FORMATO_MANIFESTO, versao_formato: N.VERSAO_MANIFESTO, desenhos: [] };
    m.atualizado_em = hoje();
    var blob = new Blob([JSON.stringify(m, null, 2) + '\n'], { type: 'application/json' });
    var a = el('a', { href: URL.createObjectURL(blob), download: 'manifesto-desenhos-placards-' + hoje() + '.json' });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
    estado.manifestoAlterado = false;
    renderDesenhos();
    avisar('Manifesto exportado (somente metadados; nenhum PDF é incluído).', 'ok');
  }

  function importarManifesto(ev) {
    var arq = ev.target.files && ev.target.files[0];
    ev.target.value = '';
    if (!arq) return;
    arq.text().then(function (txt) {
      var obj;
      try { obj = JSON.parse(txt); } catch (e) {
        estado.ultimaValidacao = { erros: [{ caminho: arq.name, mensagem: 'JSON inválido: ' + e.message }], avisos: [] };
        renderDesenhos(); return;
      }
      var res = aplicarManifesto(obj, 'importado de ' + arq.name);
      estado.ultimaValidacao = res;
      if (!res.erros.length) { estado.manifestoAlterado = false; avisar('Manifesto “' + arq.name + '” aplicado.', 'ok'); }
      renderDesenhos(); renderFicha();
    });
  }

  function definirAtiva(topo, rev) {
    estado.manifesto.desenhos.forEach(function (d) { if (d.topo === topo) d.ativa = d.revisao === rev; });
    estado.manifestoAlterado = true;
    renderDesenhos(); renderFicha();
    avisar('Revisão ativa de ' + topo + ': ' + rev + '.', 'ok');
  }

  function removerDesenho(topo, rev) {
    estado.manifesto.desenhos = estado.manifesto.desenhos.filter(function (d) { return !(d.topo === topo && d.revisao === rev); });
    var chave = N.chaveDesenho(topo, rev), a = estado.arquivos.get(chave);
    if (a) { URL.revokeObjectURL(a.url); estado.arquivos.delete(chave); }
    estado.manifestoAlterado = true;
    renderDesenhos(); renderFicha();
  }

  function renderDesenhos() {
    var corpo = limpar($('desenhos-corpo'));
    var m = estado.manifesto;
    corpo.appendChild(el('div', { class: 'painel-corpo' }, [
      el('p', { texto: 'O manifesto guarda configuração, topo, revisão, origem do PDF e o mapa explícito {folha: página do PDF} (páginas começam em 1). Folha não é deduzida da página. Nenhum link é carregado automaticamente.' }),
      el('p', { texto: 'Origens HTTPS autorizadas para PDF: ' + (origens.length ? origens.join(', ') : 'nenhuma (somente PDF local selecionado nesta sessão).') }),
      el('p', { texto: 'Manifesto: ' + (m ? m.desenhos.length + ' desenho(s), ' + estado.manifestoOrigem : 'nenhum carregado') + '.' + (estado.manifestoAlterado ? ' Há alterações não exportadas.' : '') })
    ]));
    var inputImp = el('input', { type: 'file', id: 'importar-manifesto', accept: '.json,application/json', onchange: importarManifesto });
    corpo.appendChild(el('div', { class: 'acoes' }, [
      el('label', { for: 'importar-manifesto', texto: 'Importar manifesto (JSON):' }), inputImp,
      el('button', { type: 'button', texto: 'Exportar manifesto', onclick: exportarManifesto, id: 'exportar-manifesto' }),
      el('button', { type: 'button', texto: 'Nova revisão…', onclick: function () { abrirEditor(null, ''); } })]));
    if (estado.ultimaValidacao) corpo.appendChild(listaMensagens(estado.ultimaValidacao));

    var topos = estado.toposBase.slice();
    (m ? m.desenhos : []).forEach(function (d) { if (topos.indexOf(d.topo) < 0) topos.push(d.topo); });
    if (!topos.length) { corpo.appendChild(el('p', { class: 'vazio', texto: 'Sem topos na base nem no manifesto.' })); }
    else {
      var tb = el('tbody');
      topos.forEach(function (topo) {
        var revs = m ? m.desenhos.filter(function (d) { return d.topo === topo; }) : [];
        if (!revs.length) {
          tb.appendChild(el('tr', {}, [el('th', { scope: 'row', class: 'nowrap', texto: topo }), el('td', { colspan: '5', class: 'estado-desenho ruim', texto: 'PDF não associado' }),
            el('td', {}, [el('button', { type: 'button', texto: 'Associar…', onclick: function () { abrirEditor(null, topo); } })])]));
          return;
        }
        revs.forEach(function (d) {
          var chave = N.chaveDesenho(d.topo, d.revisao), arq = estado.arquivos.get(chave);
          var nMap = Object.keys(d.mapa_folhas).length;
          var radio = el('input', { type: 'radio', name: 'ativa-' + topo, checked: d.ativa, 'aria-label': 'Revisão ' + d.revisao + ' ativa para ' + topo,
            onchange: function () { definirAtiva(d.topo, d.revisao); } });
          var pdfSessao;
          if (d.origem.tipo === 'url') pdfSessao = el('span', { class: N.origemAutorizada(d.origem.url, origens) ? '' : 'estado-desenho ruim',
            texto: N.origemAutorizada(d.origem.url, origens) ? 'URL autorizada (abre só ao clicar)' : 'URL não autorizada' });
          else pdfSessao = arq ? el('span', { texto: 'Selecionado: ' + arq.nome }) : el('span', { class: 'estado-desenho atencao', texto: 'Precisa selecionar novamente' });
          var acoes = [];
          if (d.origem.tipo === 'local') acoes.push(el('button', { type: 'button', texto: arq ? 'Trocar PDF…' : 'Selecionar PDF…', onclick: function () { pedirPdf(d); } }));
          var s = N.resolverDesenho({ desenhos: [Object.assign({}, d, { ativa: true })] }, d.topo, null, estado.arquivos, origens);
          if (s.estado === 'OK') acoes.push(botaoDocumentoInteiro(s, 'Documento inteiro'));
          acoes.push(el('button', { type: 'button', texto: 'Editar…', onclick: function () { abrirEditor(d, d.topo); } }));
          acoes.push(el('button', { type: 'button', texto: 'Remover', onclick: function () { removerDesenho(d.topo, d.revisao); } }));
          tb.appendChild(el('tr', {}, [el('th', { scope: 'row', class: 'nowrap', texto: topo }), el('td', { texto: d.revisao }), el('td', {}, [radio]),
            el('td', { texto: d.origem.tipo === 'local' ? 'Local: ' + d.origem.nome_arquivo : d.origem.url }),
            el('td', { texto: nMap + ' de ' + N.NUM_FOLHAS }), el('td', { texto: d.vinculo_conferido ? 'Sim' + (d.conferido_por ? ' (' + d.conferido_por + ')' : '') : 'Não conferido' }),
            el('td', {}, [pdfSessao, el('div', { class: 'acoes' }, acoes)])]));
        });
      });
      corpo.appendChild(el('table', {}, [el('caption', { texto: 'Revisões por topo — marque a revisão ativa.' }),
        el('thead', {}, [el('tr', {}, ['Topo', 'Revisão', 'Ativa', 'Origem do PDF', 'Folhas mapeadas', 'Vínculo', 'PDF / ações'].map(function (t) { return el('th', { scope: 'col', texto: t }); }))]), tb]));
    }
    corpo.appendChild(el('div', { id: 'editor-desenho' }));
    if (estado.editando) renderEditor();
  }

  function abrirEditor(desenho, topo) {
    estado.editando = { original: desenho, topo: topo };
    $('painel-desenhos').open = true;
    renderEditor();
    var c = $('ed-topo'); if (c) c.focus();
  }

  function renderEditor() {
    var cx = $('editor-desenho'); if (!cx) return; limpar(cx);
    var ed = estado.editando, d = ed.original || { configuracao: 'CD', topo: ed.topo, revisao: '', ativa: !(estado.manifesto && estado.manifesto.desenhos.some(function (x) { return x.topo === ed.topo && x.ativa; })),
      origem: { tipo: 'local', nome_arquivo: '', sha256: '' }, total_paginas: null, mapa_folhas: {}, vinculo_conferido: false, conferido_por: '', conferido_em: '', observacoes: '' };
    var dl = el('datalist', { id: 'lista-topos' }, estado.toposBase.map(function (t) { return el('option', { value: t }); }));
    function campo(id, rot, attrs) { return el('label', { for: id }, [rot, el('input', Object.assign({ id: id }, attrs))]); }
    var grade = el('div', { class: 'grade-mapa' });
    for (var n = 1; n <= N.NUM_FOLHAS; n++) {
      var v = d.mapa_folhas[String(n)];
      grade.appendChild(el('label', { for: 'ed-f' + n }, ['Folha ' + n, el('input', { id: 'ed-f' + n, type: 'number', min: '1', step: '1', inputmode: 'numeric', value: v === undefined ? '' : String(v), 'aria-label': 'Página do PDF para a folha ' + n })]));
    }
    var form = el('form', { id: 'form-desenho', onsubmit: function (e) { e.preventDefault(); salvarEditor(); } }, [
      el('fieldset', {}, [el('legend', { texto: ed.original ? 'Editar ' + d.topo + ' rev. ' + d.revisao : 'Nova revisão de desenho' }), dl,
        el('div', { class: 'form-linha' }, [
          el('span', { texto: 'Configuração: CD' }),
          campo('ed-topo', 'Topo ', { type: 'text', list: 'lista-topos', value: d.topo || '', required: true, size: '22' }),
          campo('ed-rev', 'Revisão ', { type: 'text', value: d.revisao || '', required: true, size: '6' }),
          el('label', {}, [el('input', { type: 'checkbox', id: 'ed-ativa', checked: d.ativa }), ' Revisão ativa'])]),
        el('div', { class: 'form-linha', role: 'radiogroup', 'aria-label': 'Origem do PDF' }, [
          el('label', {}, [el('input', { type: 'radio', name: 'ed-tipo', value: 'local', checked: d.origem.tipo !== 'url' }), ' PDF local']),
          campo('ed-nome', 'Nome do arquivo ', { type: 'text', value: d.origem.nome_arquivo || '', size: '30' }),
          el('label', {}, [el('input', { type: 'radio', name: 'ed-tipo', value: 'url', checked: d.origem.tipo === 'url' }), ' URL HTTPS corporativa']),
          campo('ed-url', 'URL ', { type: 'url', value: d.origem.url || '', size: '40' })]),
        el('div', { class: 'form-linha' }, [campo('ed-total', 'Total de páginas do PDF (opcional) ', { type: 'number', min: '1', step: '1', value: d.total_paginas || '' })]),
        el('p', { class: 'dica', texto: 'Mapa folha → página do PDF (base 1). Deixe em branco a folha sem página conhecida; não suponha folha = página.' }),
        grade,
        el('div', { class: 'form-linha' }, [
          el('label', {}, [el('input', { type: 'checkbox', id: 'ed-conf', checked: d.vinculo_conferido }), ' Vínculo conferido contra o PDF liberado']),
          campo('ed-confpor', 'Conferido por ', { type: 'text', value: d.conferido_por || '' }),
          campo('ed-confem', 'Em ', { type: 'date', value: d.conferido_em || '' })]),
        el('div', { class: 'form-linha' }, [el('label', { for: 'ed-obs' }, ['Observações ', el('textarea', { id: 'ed-obs', rows: '2', cols: '50' }, [d.observacoes || ''])])]),
        el('div', { id: 'ed-msgs' }),
        el('div', { class: 'acoes' }, [el('button', { type: 'submit', class: 'primario', texto: 'Validar e salvar' }),
          el('button', { type: 'button', texto: 'Cancelar', onclick: function () { estado.editando = null; limpar($('editor-desenho')); } })])])]);
    cx.appendChild(form);
  }

  function salvarEditor() {
    var ed = estado.editando, orig = ed.original;
    var tipo = document.querySelector('input[name="ed-tipo"]:checked').value;
    var mapa = {};
    for (var n = 1; n <= N.NUM_FOLHAS; n++) {
      var v = $('ed-f' + n).value.trim();
      if (v !== '') mapa[String(n)] = /^\d+$/.test(v) ? Number(v) : v;
    }
    var tot = $('ed-total').value.trim();
    var nova = {
      configuracao: 'CD', topo: $('ed-topo').value, revisao: $('ed-rev').value, ativa: $('ed-ativa').checked,
      origem: tipo === 'local' ? { tipo: 'local', nome_arquivo: $('ed-nome').value, sha256: orig && orig.origem.tipo === 'local' && orig.origem.nome_arquivo === $('ed-nome').value.trim() ? orig.origem.sha256 : '' }
        : { tipo: 'url', url: $('ed-url').value },
      total_paginas: tot === '' ? undefined : (/^\d+$/.test(tot) ? Number(tot) : tot),
      mapa_folhas: mapa, vinculo_conferido: $('ed-conf').checked, conferido_por: $('ed-confpor').value, conferido_em: $('ed-confem').value, observacoes: $('ed-obs').value
    };
    var topoN = N.normalizarTopo(nova.topo);
    var desenhos = (estado.manifesto ? estado.manifesto.desenhos : []).filter(function (d) { return d !== orig; }).map(function (d) {
      var c = JSON.parse(JSON.stringify(d));
      if (nova.ativa && c.topo === topoN) c.ativa = false;
      if (c.total_paginas === null) delete c.total_paginas;
      return c;
    });
    desenhos.push(nova);
    var cand = { formato: N.FORMATO_MANIFESTO, versao_formato: N.VERSAO_MANIFESTO, atualizado_em: estado.manifesto ? estado.manifesto.atualizado_em : '', desenhos: desenhos };
    var antigosArq = new Map(estado.arquivos);
    var res = aplicarManifesto(cand, 'editado nesta sessão');
    if (res.erros.length) { limpar($('ed-msgs')).appendChild(listaMensagens(res)); return; }
    // Se a chave topo|rev mudou, o PDF selecionado não é reaproveitado.
    if (orig && (orig.topo !== topoN || orig.revisao !== nova.revisao.trim().toUpperCase())) {
      var a = antigosArq.get(N.chaveDesenho(orig.topo, orig.revisao));
      if (a && estado.arquivos.get(N.chaveDesenho(orig.topo, orig.revisao)) === a) { URL.revokeObjectURL(a.url); estado.arquivos.delete(N.chaveDesenho(orig.topo, orig.revisao)); }
    }
    estado.manifestoAlterado = true;
    estado.editando = null;
    estado.ultimaValidacao = res.avisos.length ? { erros: [], avisos: res.avisos } : null;
    renderDesenhos(); renderFicha();
    avisar('Desenho ' + topoN + ' rev. ' + nova.revisao.trim().toUpperCase() + ' salvo. Exporte o manifesto para guardar.', 'ok');
  }

  // ---------------------------------------------------------------- CSV/TSV
  function decodificar(buf) {
    try { return new TextDecoder('utf-8', { fatal: true }).decode(buf); } catch (e) { return new TextDecoder('windows-1252').decode(buf); }
  }

  function importarArquivosCSV(ev) {
    var arquivos = Array.prototype.slice.call(ev.target.files || []);
    ev.target.value = '';
    var saida = limpar($('csv-resultado'));
    if (!arquivos.length) return;
    Promise.all(arquivos.map(function (a) { return a.arrayBuffer().then(function (b) { return { nome: a.name, texto: decodificar(b) }; }); }))
      .then(function (lidos) {
        var resultados = [], kits = {};
        for (var i = 0; i < lidos.length; i++) {
          var res;
          try { res = N.importarCSV(lidos[i].texto, lidos[i].nome); } catch (e) {
            saida.appendChild(el('div', { class: 'erro-caixa', role: 'alert', texto: 'Importação cancelada. ' + e.message })); return;
          }
          if (kits[res.kit]) { saida.appendChild(el('div', { class: 'erro-caixa', role: 'alert', texto: 'Importação cancelada: kit ' + rotuloKit(res.kit) + ' em mais de um arquivo.' })); return; }
          kits[res.kit] = true; resultados.push(res);
        }
        var resumo = {}, registros = [], exclusoes = [];
        resultados.forEach(function (r) { resumo[r.kit] = N.resumoKit(r); registros = registros.concat(r.registros); exclusoes = exclusoes.concat(r.exclusoes); });
        var base = { formato: 'base-placards-cd', versao_formato: 1, configuracao: 'CD',
          fonte: { arquivo: lidos.map(function (l) { return l.nome; }).join(', '), formato: 'csv' }, gerado_em: new Date().toISOString().slice(0, 19),
          resumo: resumo, abas_ignoradas: [], exclusoes: exclusoes, comparacao_snapshot: null, registros: registros };
        definirBase(base, 'csv');
        saida.appendChild(el('div', { class: 'ok-caixa', texto: 'Base importada: ' + Object.keys(resumo).map(function (k) { return rotuloKit(k) + ' ' + resumo[k].registros + ' registros (' + resumo[k].exclusoes + ' exclusões)'; }).join('; ') + '.' }));
      });
  }

  // ---------------------------------------------------------------- sobre a base
  function renderFonte() {
    var c = limpar($('fonte-corpo')), b = estado.base;
    if (!b) { c.appendChild(el('p', { class: 'nao-inf', texto: 'Base não carregada.' })); return; }
    var f = b.fonte || {};
    var dl = el('dl', { class: 'campos' });
    [['Arquivo', f.arquivo], ['Formato', f.formato], ['SHA-256', f.sha256], ['Tamanho (bytes)', f.tamanho_bytes ? String(f.tamanho_bytes) : ''],
      ['Modificado em', f.modificado_em ? dataHora(f.modificado_em) : ''], ['Importado em', dataHora(b.gerado_em)], ['Configuração', b.configuracao]]
      .forEach(function (x) { dl.appendChild(el('dt', { texto: x[0] })); dl.appendChild(el('dd', {}, [valor(x[1])])); });
    c.appendChild(dl);
    var tb = el('tbody');
    Object.keys(b.resumo).forEach(function (k) {
      var r = b.resumo[k];
      tb.appendChild(el('tr', {}, [el('th', { scope: 'row', texto: rotuloKit(k) }), el('td', { texto: r.aba }), el('td', { texto: String(r.registros) }),
        el('td', { texto: String(r.sem_pn_novo) }), el('td', { texto: String(r.sem_descricao) }), el('td', { texto: String(r.provisorios) }),
        el('td', { texto: String(r.com_divergencia_quantidade) }), el('td', { texto: String(r.exclusoes) }),
        el('td', { texto: Object.keys(r.topos).map(function (t) { return t + ' (' + r.topos[t] + ')'; }).join('; ') })]));
    });
    c.appendChild(el('table', {}, [el('caption', { texto: 'Contagens por kit (calculadas da fonte, sem ajuste).' }),
      el('thead', {}, [el('tr', {}, ['Kit', 'Aba', 'Registros CD', 'Sem PN novo', 'Sem descrição', 'Provisórios', 'Divergência de qtd.', 'Exclusões', 'Topos'].map(function (t) { return el('th', { scope: 'col', texto: t }); }))]), tb]));
    var comp = b.comparacao_snapshot;
    if (comp) {
      if (comp.diferencas.length) c.appendChild(el('div', { class: 'avisos' }, [el('strong', { texto: 'Diferenças em relação ao snapshot conferido (reportadas, não corrigidas):' }),
        el('ul', {}, comp.diferencas.map(function (d) { return el('li', { texto: d }); }))]));
      else c.appendChild(el('p', { class: 'ok-caixa', texto: 'Contagens iguais às do snapshot conferido.' }));
    }
    var avisosLayout = [];
    Object.keys(b.resumo).forEach(function (k) { (b.resumo[k].avisos_layout || []).forEach(function (a) { avisosLayout.push(rotuloKit(k) + ': ' + a); }); });
    if (avisosLayout.length) c.appendChild(el('div', { class: 'avisos' }, [el('strong', { texto: 'Avisos de layout:' }), el('ul', {}, avisosLayout.map(function (a) { return el('li', { texto: a }); }))]));
    if (b.abas_ignoradas && b.abas_ignoradas.length) {
      c.appendChild(el('h4', { texto: 'Abas ignoradas' }));
      c.appendChild(el('ul', {}, b.abas_ignoradas.map(function (a) { return el('li', { texto: a.aba + ' — ' + a.motivo }); })));
    }
    c.appendChild(el('h4', { texto: 'Linhas excluídas (' + b.exclusoes.length + ')' }));
    if (b.exclusoes.length) {
      var lim = 500, tbe = el('tbody');
      b.exclusoes.slice(0, lim).forEach(function (e) {
        tbe.appendChild(el('tr', {}, [el('td', { texto: e.aba }), el('td', { texto: String(e.linha) }), el('td', { texto: e.motivo }),
          el('td', {}, [valor(e.a)]), el('td', {}, [valor(e.c)]), el('td', {}, [valor(e.h)])]));
      });
      c.appendChild(el('table', {}, [el('thead', {}, [el('tr', {}, ['Aba', 'Linha', 'Motivo', 'A', 'C', 'H'].map(function (t) { return el('th', { scope: 'col', texto: t }); }))]), tbe]));
      if (b.exclusoes.length > lim) c.appendChild(el('p', { class: 'dica', texto: 'Exibindo ' + lim + ' de ' + b.exclusoes.length + '. Lista completa em relatorio_importacao.md.' }));
    }
  }

  // ---------------------------------------------------------------- inicialização
  function navegarLista(ev) {
    if (ev.key !== 'ArrowDown' && ev.key !== 'ArrowUp') return;
    var itens = Array.prototype.slice.call(document.querySelectorAll('#lista .item'));
    if (!itens.length) return;
    var i = itens.indexOf(document.activeElement);
    if (ev.target === $('busca')) { if (ev.key === 'ArrowDown') { ev.preventDefault(); itens[0].focus(); } return; }
    if (i < 0) return;
    ev.preventDefault();
    if (ev.key === 'ArrowDown' && i < itens.length - 1) itens[i + 1].focus();
    if (ev.key === 'ArrowUp') (i > 0 ? itens[i - 1] : $('busca')).focus();
  }

  function iniciar() {
    $('estado-base').insertAdjacentElement('afterend', el('div', { id: 'aviso-global', role: 'status', 'aria-live': 'polite' }));
    var tempo;
    $('form-busca').addEventListener('submit', function (e) { e.preventDefault(); executarBusca(); });
    $('busca').addEventListener('input', function () { clearTimeout(tempo); tempo = setTimeout(executarBusca, 120); });
    ['f-kit', 'f-topo', 'f-folha', 'f-avisos'].forEach(function (id) { $(id).addEventListener('change', function () { executarBusca(); renderFicha(); }); });
    $('limpar').addEventListener('click', limparTudo);
    $('mais').addEventListener('click', function () { estado.limite += 100; executarBusca(true); });
    $('vis-fechar').addEventListener('click', fecharVisualizador);
    $('seletor-pdf').addEventListener('change', aoSelecionarPdf);
    $('arquivo-csv').addEventListener('change', importarArquivosCSV);
    document.addEventListener('keydown', navegarLista);

    var man = lerJSON('dados-manifesto');
    var base = lerJSON('dados-base');
    definirBase(base && base.registros ? base : null, 'incorporada');
    if (man) {
      var res = aplicarManifesto(man, 'incorporado no HTML');
      if (res.erros.length) { estado.ultimaValidacao = res; avisar('O manifesto incorporado é inválido e foi ignorado.', 'erro'); }
      renderDesenhos(); renderFicha();
    }
  }

  iniciar();
})();
