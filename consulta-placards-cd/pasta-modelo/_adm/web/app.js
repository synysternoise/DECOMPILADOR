/* Consulta de Placards CD — interface. Texto da planilha entra sempre escapado. */
(function () {
  'use strict';
  var B = window.BuscaPlacards;
  var $ = function (id) { return document.getElementById(id); };
  var dados = null;
  try { dados = JSON.parse($('dados').textContent); } catch (e) { dados = null; }

  var KIT = { PLASTICO: ['pl', 'Plástico'], METALICO: ['me', 'Metálico'] };
  var SETA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg>';
  function esc(x) {
    return String(x).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; });
  }
  function dataBR(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '');
    return m ? m[3] + '/' + m[2] + '/' + m[1] : '';
  }

  // Rodapé do desenvolvedor
  var dev = (dados && dados.desenvolvedor) || {};
  $('dev-sig').textContent = dev.iniciais || 'DEV';
  $('dev-txt').innerHTML = dev.nome
    ? 'Desenvolvido por ' + esc(dev.nome) + '<small>' + esc(dev.contato || '') + '</small>'
    : 'Espaço do desenvolvedor<small>Nome e contato: preencher em _adm/config.json</small>';
  $('versao').textContent = 'v' + ((dados && dados.versao_app) || '1.0') + (dados ? ' · base de ' + dataBR(dados.gerado_em) : '');

  if (!dados || !dados.registros) {
    $('meta').innerHTML = '<div class="nao-pub"><b>Consulta ainda não publicada.</b> O administrador precisa rodar <b>_adm\\ATUALIZAR CONSULTA.bat</b> com a planilha na pasta.</div>';
    $('q').disabled = true;
    $('contagem').textContent = '';
    return;
  }

  var indice = B.preparar(dados.registros);
  var idiomas = B.idiomasPresentes(indice);
  var idioma = '';
  $('meta').textContent = dados.registros.length + ' placards · ' + dados.total_desenhos + ' desenhos 2D · base atualizada pelo ADM em ' + dataBR(dados.gerado_em);
  $('idiomas').innerHTML = [''].concat(idiomas).map(function (l) {
    return '<button type="button" aria-pressed="' + (l === idioma) + '" data-l="' + esc(l) + '">' + (l ? esc(l) : 'Todos') + '</button>';
  }).join('');

  function card(x) {
    var r = x.registro, exato = x.pontuacao >= 100, k = KIT[r.kit] || ['pl', r.kit];
    var folhas = r.folhas.filter(function (f) { return f.aparece; }).map(function (f) {
      return f.numero === null
        ? '<span class="sh">SH' + (f.folha < 10 ? '0' : '') + f.folha + '<small class="txt">' + esc(f.texto) + '</small></span>'
        : '<span class="sh">SH' + (f.folha < 10 ? '0' : '') + f.folha + '<small>× ' + esc(f.texto) + '</small></span>';
    }).join('');
    var topo = (r.topo_normalizado || '').split('/')[0];
    return '<article class="card' + (exato ? ' exato' : '') + '">' +
      '<div class="l1"><span class="kit ' + k[0] + '"><i></i>' + k[1] + '</span>' + (exato ? '<span class="exato-tag">Correspondência exata</span>' : '') + '</div>' +
      (r.pn_novo ? '<div class="pn">' + esc(r.pn_novo) + '</div>' : '<div class="pn sem">Sem PN novo</div>') +
      (r.pn_antigo ? '<div class="cdpl">' + esc(r.pn_antigo) + '</div>' : '') +
      '<div class="titulo' + (r.descricao ? '' : ' sem') + '">' + (r.descricao ? esc(r.descricao) : 'Título não informado na planilha') + '</div>' +
      (x.idiomas.length ? '<div class="langs">' + x.idiomas.map(function (l) { return '<span class="lang">' + esc(l) + '</span>'; }).join('') + '</div>' : '') +
      '<div class="dados"><div><span>POS</span><b>' + esc(r.pos || '—') + '</b></div><div><span>Zona</span><b>' + esc(r.zona || '—') + '</b></div><div><span>Topo</span><b>' + esc(topo || '—') + '</b></div></div>' +
      '<div class="folhas"><span>Folhas</span>' + (folhas || '<span class="sh"><small>não informadas</small></span>') + '</div>' +
      (r.desenho
        ? '<a class="abrir" href="' + esc(r.desenho) + '" target="_blank" rel="noopener noreferrer">Abrir desenho 2D ' + SETA + '</a>'
        : '<span class="abrir off">Sem desenho 2D</span>') +
      '</article>';
  }

  function render() {
    var q = $('q').value, res = B.buscar(indice, q, idioma);
    $('contagem').innerHTML = '<b>' + res.length + '</b>placard' + (res.length === 1 ? '' : 's');
    $('grade').innerHTML = res.length ? res.map(card).join('')
      : '<div class="vazio">Nenhum placard encontrado' + (q.trim() ? ' para “' + esc(q.trim()) + '”' : '') + (idioma ? ' em ' + esc(idioma) : '') + '.</div>';
  }

  var t;
  $('q').addEventListener('input', function () { clearTimeout(t); t = setTimeout(render, 90); });
  $('idiomas').addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b) return;
    idioma = b.getAttribute('data-l');
    Array.prototype.forEach.call($('idiomas').querySelectorAll('button'), function (x) { x.setAttribute('aria-pressed', String(x.getAttribute('data-l') === idioma)); });
    render();
  });
  render();
  $('q').focus();
})();
