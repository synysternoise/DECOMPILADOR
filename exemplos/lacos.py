def a(x):
    i = j = len(x)
    assert i, "vazio"
    n = 0
    while x or i > -3:
        i -= 1
        n += 1
        if i < 0:
            continue
        x = x[1:]
    for k in range(3):
        for m in range(k):
            if m == 1:
                break
            n += m
    return n, i, j
print(a([1, 2]), a("abcdef"))
