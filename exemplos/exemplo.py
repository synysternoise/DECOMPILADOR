"""Programa de exemplo usado para testar o descompilador."""
import math
import os.path as caminho
from collections import OrderedDict, namedtuple as nt

LIMITE = 10
nomes = ["ana", "bia", "caio"]
idades = {"ana": 31, "bia": 25}
ponto = (1, 2.5, -3)
vazio = []


def fatorial(n):
    """Calcula o fatorial de n."""
    if n <= 1:
        return 1
    return n * fatorial(n - 1)


def classificar(nota, bonus=0, *extras, arredondar=True, **opcoes):
    total = nota + bonus + sum(extras)
    if arredondar:
        total = round(total)
    if total >= 9:
        return "ótimo"
    elif total >= 7:
        return "bom"
    elif total >= 5 and not opcoes.get("rigoroso"):
        return "regular"
    else:
        return "ruim"


def primos(maximo):
    achados = []
    n = 2
    while n < maximo:
        divisor = 2
        eh_primo = True
        while divisor * divisor <= n:
            if n % divisor == 0:
                eh_primo = False
                break
            divisor += 1
        if eh_primo:
            achados.append(n)
        n += 1
    return achados


def procurar(lista, alvo):
    for posicao, item in enumerate(lista):
        if item == alvo:
            print(f"achei {alvo!r} na posição {posicao:>3}")
            break
    else:
        print("não achei", alvo)
    contador = 0
    for item in lista:
        if not item:
            continue
        if item is None or len(item) > 3:
            contador += 2
        else:
            contador += 1
    return contador


class Animal:
    """Um animal qualquer."""
    patas = 4

    def __init__(self, nome, som="..."):
        self.nome = nome
        self.som = som
        self.energia = 3

    def falar(self):
        self.energia -= 1
        return f"{self.nome} faz {self.som}"


class Cachorro(Animal):
    def __init__(self, nome):
        super().__init__(nome, "au au")

    def falar(self):
        return super().falar().upper()


def calculos(a, b):
    global LIMITE
    LIMITE = LIMITE + 1
    x = (a + b) * (a - b) / 2 ** 3 % 7
    y = -a if a > b else b
    z = a or b
    w = a and b
    lista = [a, b, *nomes]
    lista[0] += 5
    primeiro, segundo = lista[0], lista[1]
    primeiro, segundo = segundo, primeiro
    dobro = lambda v, k=2: v * k
    parte = nomes[1:]
    i = j = 0
    while True:
        i += 1
        if i > 3:
            break
    del lista[0]
    assert x is not None, "x vazio"
    return x, y, z, w, primeiro, segundo, dobro(4), parte, i, j, math.floor(2.7), lista


print(fatorial(5), classificar(6.4, 1, 1, 0.2), classificar(5, rigoroso=True))
print(primos(30))
print(procurar(nomes, "bia"), procurar(nomes + ["", "joão"], "x"))
rex = Cachorro("Rex")
print(rex.falar(), rex.energia, Animal.patas, Animal.__doc__)
print(calculos(7, 3), LIMITE)
print(caminho.basename("/a/b.txt"), OrderedDict(a=1), nt("P", "x y")(1, 2))
print(sorted(idades.items()), ponto, vazio, max(*ponto, 9), dict(**idades, z=1))
if __name__ == "__main__":
    print("fim")
