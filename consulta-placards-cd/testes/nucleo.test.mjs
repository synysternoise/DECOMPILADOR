// Testes do núcleo JS (node --test). Dados SINTÉTICOS.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const aqui = dirname(fileURLToPath(import.meta.url));
const N = createRequire(import.meta.url)(join(aqui, '..', 'web', 'nucleo.js'));
const CASOS = JSON.parse(readFileSync(join(aqui, 'casos_manifesto.json'), 'utf8')).casos;

const SH = Array.from({ length: 20 }, (_, i) => 'SH' + (i + 1));
function linhaCSV(cols) { return cols.map(c => /[;"\n]/.test(c) ? '"' + c.replace(/"/g, '""') + '"' : c).join(';'); }
function csv(kit, linhas) {
  const cab = ['PART NUMBER', 'E2 REFERENCIA', kit === 'P' ? 'CDPL (REF)' : 'PART NUMBER', 'POS', 'ZONE', 'QTY', 'FORMATO',
    kit === 'P' ? 'CONJUNTO' : 'MATERIAL', 'ECODE', 'ACTION', 'LIBERADO', ...SH, 'Total', 'Check', 'OBS'];
  return [cab, ...linhas].map(linhaCSV).join('\r\n') + '\r\n';
}
function L(a, b, c, pos, zona, qty, g, h, folhas, total) {
  const sh = Array(20).fill('');
  Object.entries(folhas).forEach(([f, q]) => { sh[f - 1] = String(q); });
  return [a, b, c, pos, zona, qty, g, h, '1', 'SIM', 'OK', ...sh, total, 'ok', ''];
}
const TP = '171-60473-401/ CD', TM = '171-60474-401/ CD';
const plast = csv('P', [
  L('171-50557-021', '196-LEX003131', 'CDPL569-1-16', '00122', 'F204', '1', 'SEAT ROW 16; "B" LH', TP, { 20: 1 }, '1'),
  L('171-50557-0210', '', 'CDPL569-11-6', '00123', 'F205', '1', 'REF 171-50557-021 NA DESCRIÇÃO', TP, { 19: 1 }, '1'),
  L('', '196-LEX002446', 'CDPL561-27', '00006', 'B034', '4', 'AÇÃO PROIBIDA\nSEGUNDA LINHA', TP, { 3: 2, 4: 2 }, '4'),
  L('171-50999-001', '', 'CDPL999-1', '00001', 'A001', '1', 'LX', '171-60473-401/ LX', { 20: 1 }, '1'),
  L('171-59130-001', '', 'CDPL9130-1', '00230', 'C303', '3', 'DIVERGENTE', TP, { 6: 1, 7: 1 }, '4'),
]);
const metal = csv('M', [
  L('171-60555-001', '', 'CDPL568-005', '00505', 'M105', '4', 'METALICO', TM, { 6: 1, 7: 1, 9: 1, 11: 1 }, '4'),
  L('', '', 'CDPL568-201', '00509', 'M109', '1', '', TM, { 2: 1 }, '1'),
]);
const rp = N.importarCSV(plast, 'plastico.csv'), rm = N.importarCSV(metal, 'metalico.csv');
const regs = rp.registros.concat(rm.registros);
const ix = N.indexar(regs);
const ids = (res) => res.map(x => x.registro.pn_novo || x.registro.pn_antigo);

test('CSV: kit pelo cabeçalho, aspas, ; e quebra de linha no campo, LX excluído', () => {
  assert.equal(rp.kit, 'PLASTICO'); assert.equal(rm.kit, 'METALICO');
  assert.equal(rp.registros.length, 4); assert.equal(rp.exclusoes.length, 1);
  assert.match(rp.exclusoes[0].motivo, /LX/);
  assert.equal(rp.registros[0].descricao, 'SEAT ROW 16; "B" LH');
  assert.equal(rp.registros[2].descricao, 'AÇÃO PROIBIDA\nSEGUNDA LINHA');
  assert.equal(rp.registros[0].pos, '00122');
  assert.equal(rp.registros[0].linha, 2);
});

test('CSV: layout inválido é recusado', () => {
  const ruim = plast.replace('SH12', 'XX12');
  assert.throws(() => N.importarCSV(ruim, 'x.csv'), /SH12/);
  assert.throws(() => N.importarCSV('a;b\n1;2\n', 'y.csv'), /kit/);
});

test('busca: critério 2 com e sem hífens, caixa e espaços', () => {
  for (const q of ['171-50557-021', '17150557021', ' 171 50557 021 ', 'cdpl569-1-16', 'CDPL569116', 'cdpl 569 1 16']) {
    const res = N.buscar(ix, q, {});
    assert.equal(res[0].registro.pn_novo, '171-50557-021', q);
    assert.ok(res[0].pontuacao >= 95, q);
  }
});

test('busca: exato literal antes de colisão por normalização e de prefixo/descrição', () => {
  const r1 = N.buscar(ix, 'CDPL569-1-16', {});
  assert.deepEqual(r1.slice(0, 2).map(x => [x.registro.pn_antigo, x.pontuacao]), [['CDPL569-1-16', 100], ['CDPL569-11-6', 95]]);
  const r2 = N.buscar(ix, '171-50557-021', {});
  assert.deepEqual(ids(r2).slice(0, 2), ['171-50557-021', '171-50557-0210']);
  assert.ok(r2[0].pontuacao > r2[1].pontuacao);
});

test('busca: E2, descrição com acento e topo', () => {
  assert.equal(N.buscar(ix, '196lex002446', {})[0].registro.pn_antigo, 'CDPL561-27');
  assert.equal(N.buscar(ix, 'acao proibida', {})[0].registro.pn_antigo, 'CDPL561-27');
  assert.equal(N.buscar(ix, '171-60474-401/CD', {}).length, 2);
});

test('critério 3: metálico sem PN e sem descrição continua pesquisável', () => {
  const r = N.buscar(ix, 'CDPL568-201', {})[0].registro;
  assert.equal(r.pn_novo, null); assert.equal(r.descricao, null);
  const m = N.buscar(ix, '171-60555-001', {})[0].registro;
  assert.deepEqual(m.folhas.map(f => [f.folha, f.numero]), [[6, 1], [7, 1], [9, 1], [11, 1]]);
});

test('filtros combinados e folha não esconde as demais folhas', () => {
  const res = N.buscar(ix, '', { kit: 'METALICO', topo: '171-60474-401/CD', folha: '9' });
  assert.deepEqual(ids(res), ['171-60555-001']);
  assert.equal(res[0].registro.folhas.length, 4);
  assert.equal(N.buscar(ix, '', { kit: 'PLASTICO', folha: '9' }).length, 0);
  assert.equal(N.buscar(ix, 'CDPL568-201', { kit: 'PLASTICO' }).length, 0);
  assert.deepEqual(ids(N.buscar(ix, '', { somenteAvisos: true, kit: 'PLASTICO' })), ['CDPL561-27', '171-59130-001']);
  assert.equal(N.buscar(ix, 'nada-disso', {}).length, 0);
});

test('critério 4: divergência QTY × soma × Total sem correção', () => {
  const r = regs.find(x => x.pn_novo === '171-59130-001');
  assert.deepEqual([r.qty, r.soma_folhas, r.total_registrado], ['3', 2, '4']);
  assert.deepEqual(r.avisos.map(a => a.codigo).filter(c => N.CODIGOS_DIVERGENCIA.includes(c)), ['QTY_DIF_SOMA', 'TOTAL_DIF_SOMA', 'QTY_DIF_TOTAL']);
});

for (const c of CASOS) {
  test('manifesto: ' + c.nome, () => {
    const res = N.validarManifesto(c.manifesto, c.topos_base);
    assert.deepEqual([...new Set(res.erros.map(e => e.codigo))].sort(), c.erros);
    assert.deepEqual([...new Set(res.avisos.map(e => e.codigo))].sort(), c.avisos);
  });
}

function manifesto(extra) {
  const m = {
    formato: 'manifesto-desenhos-placards', versao_formato: 1, desenhos: [
      { configuracao: 'CD', topo: '171-60473-401/CD', revisao: 'A', ativa: true, origem: { tipo: 'local', nome_arquivo: 'a.pdf' },
        mapa_folhas: Object.fromEntries(Array.from({ length: 20 }, (_, i) => [String(i + 1), i + 3]).filter(([f]) => f !== '19')) },
      { configuracao: 'CD', topo: '171-60473-401/CD', revisao: 'B', ativa: false, origem: { tipo: 'local', nome_arquivo: 'b.pdf' },
        mapa_folhas: Object.fromEntries(Array.from({ length: 20 }, (_, i) => [String(i + 1), i + 4])) },
      ...(extra || [])]
  };
  const r = N.validarManifesto(m);
  assert.deepEqual(r.erros, []);
  return r.manifesto;
}

test('desenho: folha 20 → página 22, revisão ativa, mapa ausente, PDF não associado, reselecionar', () => {
  const m = manifesto();
  const T = '171-60473-401/CD';
  assert.equal(N.resolverDesenho(m, '171-60474-401/CD', 6, new Map(), []).estado, 'NAO_ASSOCIADO');
  assert.equal(N.resolverDesenho(null, T, 6, new Map(), []).estado, 'NAO_ASSOCIADO');
  const semArq = N.resolverDesenho(m, T, 20, new Map(), []);
  assert.equal(semArq.estado, 'LOCAL_NAO_SELECIONADO'); assert.equal(semArq.pagina, 22);
  const arqs = new Map([[N.chaveDesenho(T, 'A'), { url: 'blob:x/1' }], [N.chaveDesenho(T, 'B'), { url: 'blob:x/2' }]]);
  const ok = N.resolverDesenho(m, T, 20, arqs, []);
  assert.equal(ok.estado, 'OK'); assert.equal(ok.urlPagina, 'blob:x/1#page=22'); assert.equal(ok.urlDocumento, 'blob:x/1');
  const f19 = N.resolverDesenho(m, T, 19, arqs, []);
  assert.equal(f19.estado, 'FOLHA_SEM_PAGINA'); assert.equal(f19.urlDocumento, 'blob:x/1');
  const inteiro = N.resolverDesenho(m, T, null, arqs, []);
  assert.equal(inteiro.estado, 'OK'); assert.equal(inteiro.urlPagina, null);
  m.desenhos.forEach(d => { d.ativa = d.revisao === 'B'; });
  const b = N.resolverDesenho(m, T, 20, arqs, []);
  assert.equal(b.revisao, 'B'); assert.equal(b.urlPagina, 'blob:x/2#page=23');
  m.desenhos.forEach(d => { d.ativa = false; });
  assert.equal(N.resolverDesenho(m, T, 20, arqs, []).estado, 'SEM_REVISAO_ATIVA');
});

test('desenho: URL só de origem HTTPS autorizada, nunca carregada automaticamente', () => {
  const m = manifesto([{ configuracao: 'CD', topo: '171-60474-401/CD', revisao: 'C', ativa: true,
    origem: { tipo: 'url', url: 'https://desenhos.empresa.example/m.pdf#zoom=50' }, mapa_folhas: { '6': 8 } }]);
  const T = '171-60474-401/CD';
  assert.equal(N.resolverDesenho(m, T, 6, new Map(), []).estado, 'URL_NAO_AUTORIZADA');
  assert.equal(N.resolverDesenho(m, T, 6, new Map(), ['https://outro.example']).estado, 'URL_NAO_AUTORIZADA');
  const ok = N.resolverDesenho(m, T, 6, new Map(), ['https://desenhos.empresa.example']);
  assert.equal(ok.urlPagina, 'https://desenhos.empresa.example/m.pdf#page=8');
  assert.equal(N.origemAutorizada('http://desenhos.empresa.example/x.pdf', ['https://desenhos.empresa.example']), false);
});

test('normalização de busca', () => {
  assert.equal(N.normalizarBusca(' 171-50557 021 '), '17150557021');
  assert.equal(N.normalizarBusca('Ação/–x'), 'ACAOX');
  assert.deepEqual(N.extrairConfiguracao('171-60473-401 CD'), ['CD', '171-60473-401/CD']);
});
