/* Busca e idiomas da consulta de placards (sem DOM; testável no Node). */
(function (raiz) {
  'use strict';

  // Siglas de idioma que aparecem no título (coluna G)
  var IDIOMAS = { ING: 'Inglês', ENG: 'Inglês', FRA: 'Francês', FRAN: 'Francês', FR: 'Francês', ESP: 'Espanhol', SPA: 'Espanhol',
    POR: 'Português', PORT: 'Português', ALE: 'Alemão', GER: 'Alemão', ITA: 'Italiano', PIC: 'Pictórico', PICTORIAL: 'Pictórico' };

  function semAcento(s) { return String(s).normalize('NFD').replace(/[̀-ͯ]/g, ''); }

  /** Chave de busca: sem acento, maiúscula, sem espaços, hífens, pontos, barras. */
  function chave(s) {
    if (s === null || s === undefined) return '';
    return semAcento(s).toUpperCase().replace(/[\s\-_.\/\\‐-―]+/g, '');
  }

  function idiomasDoTitulo(titulo) {
    if (!titulo) return [];
    var vistos = [];
    semAcento(titulo).toUpperCase().split(/[^A-Z]+/).forEach(function (t) {
      var nome = IDIOMAS[t];
      if (nome && vistos.indexOf(nome) < 0) vistos.push(nome);
    });
    return vistos;
  }

  function preparar(registros) {
    return registros.map(function (r) {
      return { r: r, pn: chave(r.pn_novo), c: chave(r.pn_antigo), e2: chave(r.ref_e2), t: chave(r.descricao),
        palavras: semAcento(r.descricao || '').toUpperCase(), idiomas: idiomasDoTitulo(r.descricao) };
    });
  }

  function idiomasPresentes(indice) {
    var todos = [];
    indice.forEach(function (x) { x.idiomas.forEach(function (i) { if (todos.indexOf(i) < 0) todos.push(i); }); });
    return todos.sort(function (a, b) { return a.localeCompare(b, 'pt-BR'); });
  }

  function pontuar(x, q, palavras) {
    if (!q) return 1;
    if ((x.pn && x.pn === q) || (x.c && x.c === q)) return 100;
    if (x.e2 && x.e2 === q) return 90;
    if (q.length >= 3 && ((x.pn && x.pn.indexOf(q) === 0) || (x.c && x.c.indexOf(q) === 0))) return 60;
    if (q.length >= 3 && ((x.pn && x.pn.indexOf(q) >= 0) || (x.c && x.c.indexOf(q) >= 0) || (x.e2 && x.e2.indexOf(q) >= 0))) return 50;
    if (palavras.length && palavras.every(function (p) { return x.palavras.indexOf(p) >= 0; })) return 20;
    if (q.length >= 3 && x.t.indexOf(q) >= 0) return 20;
    return 0;
  }

  var ORDEM_KIT = { PLASTICO: 0, METALICO: 1 };

  /** Resultados ordenados: exatos de PN/CDPL primeiro, depois kit e linha da planilha. */
  function buscar(indice, consulta, idioma) {
    var q = chave(consulta);
    var palavras = semAcento(consulta || '').toUpperCase().split(/\s+/).filter(Boolean);
    var saida = [];
    indice.forEach(function (x) {
      if (idioma && x.idiomas.indexOf(idioma) < 0) return;
      var p = pontuar(x, q, palavras);
      if (p > 0) saida.push({ registro: x.r, pontuacao: p, idiomas: x.idiomas });
    });
    saida.sort(function (a, b) {
      return (b.pontuacao - a.pontuacao) || (ORDEM_KIT[a.registro.kit] - ORDEM_KIT[b.registro.kit]) || (a.registro.linha - b.registro.linha);
    });
    return saida;
  }

  var api = { chave: chave, idiomasDoTitulo: idiomasDoTitulo, preparar: preparar, idiomasPresentes: idiomasPresentes, buscar: buscar };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else raiz.BuscaPlacards = api;
})(this);
