/*
 * Leitor mínimo de .xlsx/.xlsm no navegador, somente leitura.
 * O arquivo é lido no próprio computador; nada é enviado. Macros nunca rodam.
 * Lê os valores que o Excel salvou no arquivo (não recalcula fórmulas).
 * Espelha placards_cd/leitores.py (formatar_valor) para que a página e o
 * importador Python produzam os mesmos registros.
 */
(function (raiz) {
  'use strict';

  var ERROS = ['#N/A', '#REF!', '#VALUE!', '#DIV/0!', '#NAME?', '#NUM!', '#NULL!', '#SPILL!', '#CALC!'];
  var FORMATOS_PADRAO = { 0: 'General', 1: '0', 2: '0.00', 3: '#,##0', 4: '#,##0.00', 9: '0%', 10: '0.00%', 11: '0.00E+00',
    12: '# ?/?', 13: '# ??/??', 14: 'mm-dd-yy', 15: 'd-mmm-yy', 16: 'd-mmm', 17: 'mmm-yy', 18: 'h:mm AM/PM', 19: 'h:mm:ss AM/PM',
    20: 'h:mm', 21: 'h:mm:ss', 22: 'm/d/yy h:mm', 37: '#,##0_);(#,##0)', 38: '#,##0_);[Red](#,##0)', 39: '#,##0.00_);(#,##0.00)',
    40: '#,##0.00_);[Red](#,##0.00)', 45: 'mm:ss', 46: '[h]:mm:ss', 47: 'mmss.0', 48: '##0.0E+0', 49: '@' };

  function ErroPlanilha(m) { this.name = 'ErroPlanilha'; this.message = m; }
  ErroPlanilha.prototype = Object.create(Error.prototype);

  // ------------------------------------------------------------------ ZIP
  function lerZip(buf) {
    var dv = new DataView(buf), n = buf.byteLength, fim = -1;
    for (var i = n - 22; i >= Math.max(0, n - 65557); i--) { if (dv.getUint32(i, true) === 0x06054b50) { fim = i; break; } }
    if (fim < 0) throw new ErroPlanilha('O arquivo não é um .xlsx válido. Se for .xls (Excel antigo), abra no Excel e salve como .xlsx.');
    var total = dv.getUint16(fim + 10, true), p = dv.getUint32(fim + 16, true), entradas = {};
    var dec = new TextDecoder('utf-8');
    for (var k = 0; k < total; k++) {
      if (dv.getUint32(p, true) !== 0x02014b50) throw new ErroPlanilha('Estrutura ZIP inválida no .xlsx.');
      var metodo = dv.getUint16(p + 10, true), tam = dv.getUint32(p + 20, true);
      var ln = dv.getUint16(p + 28, true), le = dv.getUint16(p + 30, true), lc = dv.getUint16(p + 32, true);
      var local = dv.getUint32(p + 42, true);
      var nome = dec.decode(new Uint8Array(buf, p + 46, ln));
      entradas[nome] = { metodo: metodo, tam: tam, local: local };
      p += 46 + ln + le + lc;
    }
    function extrair(nome) {
      var e = entradas[nome];
      if (!e) return Promise.resolve(null);
      var ini = e.local + 30 + dv.getUint16(e.local + 26, true) + dv.getUint16(e.local + 28, true);
      var dados = new Uint8Array(buf, ini, e.tam);
      if (e.metodo === 0) return Promise.resolve(dec.decode(dados));
      if (e.metodo !== 8) return Promise.reject(new ErroPlanilha('Compressão não suportada no .xlsx (' + e.metodo + ').'));
      if (typeof DecompressionStream === 'undefined') return Promise.reject(new ErroPlanilha('Navegador sem suporte para ler .xlsx. Use o Edge ou o Chrome atualizado.'));
      var fluxo = new Blob([dados]).stream().pipeThrough(new DecompressionStream('deflate-raw'));
      return new Response(fluxo).text();
    }
    return { nomes: Object.keys(entradas), extrair: extrair };
  }

  // ------------------------------------------------------------------ XML
  function xml(texto) {
    var d = new DOMParser().parseFromString(texto, 'application/xml');
    if (d.getElementsByTagName('parsererror').length) throw new ErroPlanilha('XML inválido dentro do .xlsx.');
    return d;
  }
  function tags(no, nome) { return Array.prototype.slice.call(no.getElementsByTagNameNS('*', nome)); }
  function filhos(no, nome) { return Array.prototype.filter.call(no.childNodes, function (c) { return c.localName === nome; }); }
  function attrId(no) {
    for (var i = 0; i < no.attributes.length; i++) { var a = no.attributes[i]; if (a.localName === 'id' && a.prefix) return a.value; }
    return no.getAttribute('r:id');
  }
  function textoSi(si) {
    // Concatena os <t>, ignorando a guia fonética (<rPh>)
    return tags(si, 't').filter(function (t) {
      for (var p = t.parentNode; p && p !== si; p = p.parentNode) if (p.localName === 'rPh') return false;
      return true;
    }).map(function (t) { return t.textContent; }).join('');
  }
  function resolver(base, alvo) {
    if (alvo.charAt(0) === '/') return alvo.slice(1);
    var partes = base.split('/'); partes.pop();
    alvo.split('/').forEach(function (s) { if (s === '..') partes.pop(); else if (s !== '.') partes.push(s); });
    return partes.join('/');
  }

  // ------------------------------------------------------------------ formatação (= leitores.py)
  var RE_LIT = '(?:"[^"]*"|\\\\.)*';
  function formatoZeros(fmt) {
    if (!fmt) return null;
    var secao = fmt.split(';')[0].replace(/\[[^\]]*\]/g, '').trim();
    var m = new RegExp('^(' + RE_LIT + ')(0+)(' + RE_LIT + ')$').exec(secao);
    if (!m) return null;
    function lit(t) { return (t.match(/"[^"]*"|\\./g) || []).map(function (a) { return a.charAt(0) === '"' ? a.slice(1, -1) : a.slice(1); }).join(''); }
    return [lit(m[1]), m[2].length, lit(m[3])];
  }
  function casasDecimais(fmt) {
    if (!fmt) return null;
    var m = /^[#,]*0+\.(0+)$/.exec(fmt.split(';')[0].trim());
    return m ? m[1].length : null;
  }
  function ehData(fmt) {
    if (!fmt) return false;
    var f = fmt.split(';')[0].replace(/".*?"|\[(?!hh?\]|mm?\]|ss?\])[^\]]*\]/g, '');
    return /(^|[^_\\])[dmhysDMHYS]/.test(f);
  }
  function p2(n) { return (n < 10 ? '0' : '') + n; }
  function dataExcel(v, base1904) {
    var ms = Math.round((v - Math.floor(v)) * 86400000), dia = Math.floor(v);
    if (!base1904 && dia > 0 && dia < 60) dia += 1;
    var t = Date.UTC(base1904 ? 1904 : 1899, base1904 ? 0 : 11, base1904 ? 1 : 30) + dia * 86400000 + ms;
    var d = new Date(t), data = d.getUTCFullYear() + '-' + p2(d.getUTCMonth() + 1) + '-' + p2(d.getUTCDate());
    if (v >= 0 && v < 1) return p2(d.getUTCHours()) + ':' + p2(d.getUTCMinutes()) + ':' + p2(d.getUTCSeconds());
    if (!ms) return data;
    return data + ' ' + p2(d.getUTCHours()) + ':' + p2(d.getUTCMinutes()) + ':' + p2(d.getUTCSeconds());
  }
  function formatarNumero(v, fmt) {
    var n = Math.round(v * 1e10) / 1e10, z = formatoZeros(fmt);
    if (Number.isInteger(n)) {
      if (z && n >= 0) { var s = String(n); while (s.length < z[1]) s = '0' + s; return z[0] + s + z[2]; }
      return String(n);
    }
    var c = casasDecimais(fmt);
    if (c !== null) return n.toFixed(c);
    return String(n);
  }

  function colunaIndice(ref) {
    var m = /^([A-Z]+)/.exec(ref || ''), n = 0;
    if (!m) return -1;
    for (var i = 0; i < m[1].length; i++) n = n * 26 + (m[1].charCodeAt(i) - 64);
    return n - 1;
  }

  // ------------------------------------------------------------------ leitura
  /** Lê o .xlsx: { abas: [nomes], ler(nome) -> Promise<linhas> }.
   *  Cada linha é uma lista de { texto, formulaSemCache }. */
  function abrir(buf) {
    var zip = lerZip(buf);
    return zip.extrair('_rels/.rels').then(function (rels) {
      var wbPath = 'xl/workbook.xml';
      if (rels) tags(xml(rels), 'Relationship').forEach(function (r) { if (/officeDocument$/.test(r.getAttribute('Type'))) wbPath = resolver('', r.getAttribute('Target')); });
      var relsPath = wbPath.replace(/[^\/]+$/, '_rels/') + wbPath.split('/').pop() + '.rels';
      return Promise.all([zip.extrair(wbPath), zip.extrair(relsPath)]).then(function (r) {
        if (!r[0]) throw new ErroPlanilha('Planilha sem workbook.xml. O arquivo é mesmo um .xlsx?');
        var wb = xml(r[0]), alvos = {};
        if (r[1]) tags(xml(r[1]), 'Relationship').forEach(function (x) { alvos[x.getAttribute('Id')] = resolver(wbPath, x.getAttribute('Target')); });
        var pr = tags(wb, 'workbookPr')[0], base1904 = !!(pr && /^(1|true)$/.test(pr.getAttribute('date1904') || ''));
        var abas = tags(wb, 'sheet').map(function (s) { return { nome: s.getAttribute('name'), caminho: alvos[attrId(s)] }; });
        var ssPath = null, stPath = null;
        Object.keys(alvos).forEach(function (k) { if (/sharedStrings\.xml$/.test(alvos[k])) ssPath = alvos[k]; if (/styles\.xml$/.test(alvos[k])) stPath = alvos[k]; });
        return Promise.all([zip.extrair(ssPath || 'xl/sharedStrings.xml'), zip.extrair(stPath || 'xl/styles.xml')]).then(function (r2) {
          var strings = r2[0] ? tags(xml(r2[0]), 'si').map(textoSi) : [];
          var formatos = {}, xfs = [];
          if (r2[1]) {
            var st = xml(r2[1]);
            tags(st, 'numFmt').forEach(function (f) { formatos[f.getAttribute('numFmtId')] = f.getAttribute('formatCode'); });
            var cx = tags(st, 'cellXfs')[0];
            if (cx) xfs = filhos(cx, 'xf').map(function (x) { var id = x.getAttribute('numFmtId') || '0'; return formatos[id] !== undefined ? formatos[id] : (FORMATOS_PADRAO[id] || 'General'); });
          }
          return {
            abas: abas.map(function (a) { return a.nome; }),
            ler: function (nome) {
              var aba = abas.filter(function (a) { return a.nome === nome; })[0];
              if (!aba || !aba.caminho) return Promise.reject(new ErroPlanilha('Aba "' + nome + '" não encontrada no arquivo.'));
              return zip.extrair(aba.caminho).then(function (t) { return lerAba(xml(t), strings, xfs, base1904); });
            }
          };
        });
      });
    });
  }

  function lerAba(doc, strings, xfs, base1904) {
    var linhas = [], proxLinha = 1;
    tags(doc, 'row').forEach(function (row) {
      var r = parseInt(row.getAttribute('r'), 10) || proxLinha;
      proxLinha = r + 1;
      var linha = [], proxCol = 0;
      filhos(row, 'c').forEach(function (c) {
        var col = c.getAttribute('r') ? colunaIndice(c.getAttribute('r')) : proxCol;
        proxCol = col + 1;
        var t = c.getAttribute('t') || 'n', vNo = filhos(c, 'v')[0], fNo = filhos(c, 'f')[0];
        var v = vNo ? vNo.textContent : null, texto = null;
        if (t === 's') texto = v === null ? null : (strings[parseInt(v, 10)] || '');
        else if (t === 'inlineStr') { var is = filhos(c, 'is')[0]; texto = is ? textoSi(is) : null; }
        else if (t === 'str' || t === 'e') texto = v;
        else if (t === 'b') texto = v === null ? null : (v === '1' ? 'VERDADEIRO' : 'FALSO');
        else if (v !== null && v !== '') {
          var num = parseFloat(v), fmt = xfs[parseInt(c.getAttribute('s') || '0', 10)] || 'General';
          texto = ehData(fmt) ? dataExcel(num, base1904) : formatarNumero(num, fmt);
        }
        if (texto !== null && t !== 'e') texto = texto.trim();
        if (texto === '') texto = null;
        linha[col] = { texto: texto, formulaSemCache: !!fNo && (v === null || v === '') };
      });
      linhas[r - 1] = linha;
    });
    for (var i = 0; i < linhas.length; i++) if (!linhas[i]) linhas[i] = [];
    return linhas;
  }

  var api = { abrir: abrir, ErroPlanilha: ErroPlanilha, ERROS: ERROS, formatarNumero: formatarNumero };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else raiz.LeitorXlsx = api;
})(this);
