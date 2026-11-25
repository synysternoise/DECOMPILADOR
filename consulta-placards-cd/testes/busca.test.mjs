import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
const B = createRequire(import.meta.url)(join(dirname(fileURLToPath(import.meta.url)), '..', 'pasta-modelo', '_adm', 'web', 'busca.js'));

const regs = [
  { kit: 'PLASTICO', linha: 2, pn_novo: '171-50557-021', pn_antigo: 'CDPL569-1-16', ref_e2: '196-LEX003131', descricao: 'SEAT ROW 16, PLST' },
  { kit: 'PLASTICO', linha: 3, pn_novo: '171-50557-0210', pn_antigo: 'CDPL569-11-7', ref_e2: '', descricao: 'REF 171-50557-021, FRA, ING' },
  { kit: 'PLASTICO', linha: 4, pn_novo: null, pn_antigo: 'CDPL561-27', ref_e2: '196-LEX002446', descricao: 'AÇÃO PROIBIDA, PICTORIAL' },
  { kit: 'METALICO', linha: 2, pn_novo: null, pn_antigo: 'CDPL568-201', ref_e2: null, descricao: null },
  { kit: 'METALICO', linha: 3, pn_novo: '171-60555-001', pn_antigo: 'CDPL568-005', ref_e2: '', descricao: 'GALLEY, POR, ING' },
];
const ix = B.preparar(regs);

test('chave ignora caixa, espaços, hífens e acentos', () => {
  assert.equal(B.chave(' 171-50557 021 '), '17150557021');
  assert.equal(B.chave('Ação/x'), 'ACAOX');
});

test('idiomas do título', () => {
  assert.deepEqual(B.idiomasDoTitulo('EXIT PLACARD, FRA, ING, PLST'), ['Francês', 'Inglês']);
  assert.deepEqual(B.idiomasDoTitulo('LAVATORY PLACARD, PICTORIAL, PLST'), ['Pictórico']);
  assert.deepEqual(B.idiomasDoTitulo('FRAN, ING'), ['Francês', 'Inglês']);
  assert.deepEqual(B.idiomasDoTitulo('INGRESS PANEL'), []);
  assert.deepEqual(B.idiomasDoTitulo(null), []);
  assert.deepEqual(B.idiomasPresentes(ix), ['Francês', 'Inglês', 'Pictórico', 'Português']);
});

test('exato de PN/CDPL primeiro, com e sem hífen', () => {
  for (const q of ['171-50557-021', '17150557021', 'cdpl569116']) {
    const r = B.buscar(ix, q, '');
    assert.equal(r[0].registro.pn_novo, '171-50557-021', q);
    assert.equal(r[0].pontuacao, 100, q);
  }
  assert.deepEqual(B.buscar(ix, '171-50557-021', '').map(x => x.registro.linha), [2, 3]);
});

test('sem PN e sem descrição continua pesquisável; descrição com acento', () => {
  assert.equal(B.buscar(ix, 'CDPL568-201', '')[0].registro.pn_antigo, 'CDPL568-201');
  assert.equal(B.buscar(ix, 'acao proibida', '')[0].registro.pn_antigo, 'CDPL561-27');
  assert.equal(B.buscar(ix, '196lex002446', '')[0].registro.pn_antigo, 'CDPL561-27');
});

test('filtro de idioma combina com a busca', () => {
  assert.deepEqual(B.buscar(ix, '', 'Inglês').map(x => x.registro.linha), [3, 3]);
  assert.equal(B.buscar(ix, '171-50557-021', 'Francês').length, 1);
  assert.equal(B.buscar(ix, 'CDPL568-201', 'Inglês').length, 0);
  assert.equal(B.buscar(ix, '', '').length, 5);
});
