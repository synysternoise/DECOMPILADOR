# Descompilador de Python

Transforma um arquivo compilado `.pyc` de volta em código-fonte Python.
É um único arquivo (`descompilador.py`) e não precisa instalar nada além do Python.

## Como usar

```bash
# 1. (opcional) gerar um .pyc para testar
python -m py_compile exemplos/exemplo.py      # cria exemplos/__pycache__/exemplo.cpython-313.pyc

# 2. descompilar
python descompilador.py exemplos/__pycache__/exemplo.cpython-313.pyc              # mostra na tela
python descompilador.py exemplos/__pycache__/exemplo.cpython-313.pyc -o saida.py  # salva em arquivo
python descompilador.py arquivo.pyc --dis                                         # mostra só o bytecode
```

**Importante:** rode o script com a mesma versão do Python que gerou o `.pyc`.
Ele foi feito e testado no **Python 3.13**; o bytecode muda a cada versão.

## Como funciona

1. **Leitura**: pula os 16 bytes de cabeçalho do `.pyc` e carrega o objeto de código com `marshal`.
2. **Desmontagem**: o módulo `dis` lista as instruções do bytecode.
3. **Simulação da pilha**: cada instrução empilha ou desempilha *textos de expressões*
   (`LOAD_FAST a`, `LOAD_FAST b`, `BINARY_OP +` vira `a + b`).
4. **Fluxo de controle**: os saltos são reagrupados em `if/elif/else`, `while`, `for`, `break` e `continue`.
5. **Geração**: as instruções reconstruídas são impressas com a indentação correta.

## O que é suportado

- Atribuições, operadores, comparações, `and`/`or`/`not`, `a if c else b`
- Listas, tuplas, dicionários, conjuntos, fatias, f-strings
- Chamadas de função (com `*args`, `**kwargs` e argumentos nomeados)
- `if/elif/else`, `while`, `for` (com `else`), `break`, `continue`
- Funções (valores padrão, `*args`, `**kwargs`, docstring, decoradores, `lambda`, `global`)
- Classes (herança, métodos, `super()`)
- `import`, `from ... import`, `assert`, `raise`, `del`, `return`

## O que ainda NÃO é suportado

- `try/except/finally` e `with`
- Compreensões de lista/dicionário e expressões geradoras
- `yield`, `async/await`, `match`
- Comparações encadeadas (`a < b < c`) e anotações de tipo (são descartadas)

Quando uma função usa algo não suportado, ela não é perdida: o cabeçalho é
gerado e o bytecode dela aparece como comentário, com o motivo.

O código descompilado é **equivalente**, mas nem sempre idêntico ao original:
comentários e nomes de formatação se perdem, e alguns `if/else` podem aparecer
reorganizados.

## Testes

```bash
python testar.py
```

Compila cada programa da pasta `exemplos/`, descompila e confere se o código
descompilado produz exatamente a mesma saída do original.

## Aviso

Use apenas em programas seus ou que você tenha autorização para analisar.
