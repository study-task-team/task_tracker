#!/usr/bin/env python3
"""PERT и метод критического пути (ЛР 1).

Формат CSV:
    id,name,o,m,p,depends_on
    A,Каркас приложения,1,2,4,
    B,Регистрация,2,3,6,A
o, m, p — оптимистическая, наиболее вероятная и пессимистическая оценки
(в днях или часах); depends_on — id предшественников через ';'.

Скрипт считает для каждой задачи E = (o + 4m + p) / 6 и sigma = (p − o) / 6,
ранние и поздние сроки (ES, EF, LS, LF), резерв, критический путь и
вероятность завершения проекта к заданному сроку (--deadline).
Опционально строит диаграмму Mermaid для вставки в Markdown (--mermaid).

Запуск:
    python pert_cpm.py ../examples/tasks.csv --deadline 20 --mermaid
"""
import argparse
import csv
import math
import sys


def phi(z):
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def load(path):
    tasks = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            o, m, p = float(r["o"]), float(r["m"]), float(r["p"])
            if not o <= m <= p:
                sys.exit(f"{r['id']}: должно выполняться o <= m <= p")
            tasks[r["id"].strip()] = {
                "name": r.get("name", "").strip(),
                "o": o, "m": m, "p": p,
                "E": (o + 4 * m + p) / 6,
                "s": (p - o) / 6,
                "deps": [d.strip() for d in (r.get("depends_on") or "").split(";") if d.strip()],
            }
    return tasks


def topo(tasks):
    order, state = [], {}

    def visit(t):
        if state.get(t) == 1:
            sys.exit(f"Цикл в зависимостях через {t}")
        if state.get(t) == 2:
            return
        state[t] = 1
        for d in tasks[t]["deps"]:
            if d not in tasks:
                sys.exit(f"{t} зависит от неизвестной задачи {d}")
            visit(d)
        state[t] = 2
        order.append(t)

    for t in tasks:
        visit(t)
    return order


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--deadline", type=float, help="срок, для которого оценить вероятность завершения")
    ap.add_argument("--mermaid", action="store_true", help="вывести граф в формате Mermaid")
    a = ap.parse_args()
    T = load(a.csv)
    order = topo(T)
    succ = {t: [] for t in T}
    for t in T:
        for d in T[t]["deps"]:
            succ[d].append(t)
    for t in order:  # прямой проход
        T[t]["ES"] = max((T[d]["EF"] for d in T[t]["deps"]), default=0.0)
        T[t]["EF"] = T[t]["ES"] + T[t]["E"]
    finish = max(T[t]["EF"] for t in T)
    for t in reversed(order):  # обратный проход
        T[t]["LF"] = min((T[s]["LS"] for s in succ[t]), default=finish)
        T[t]["LS"] = T[t]["LF"] - T[t]["E"]
        T[t]["slack"] = T[t]["LS"] - T[t]["ES"]

    print(f"{'id':<5}{'E':>6}{'σ':>6}{'ES':>7}{'EF':>7}{'LS':>7}{'LF':>7}{'резерв':>8}  задача")
    for t in order:
        x = T[t]
        mark = " *" if abs(x["slack"]) < 1e-9 else ""
        print(f"{t:<5}{x['E']:>6.2f}{x['s']:>6.2f}{x['ES']:>7.2f}{x['EF']:>7.2f}{x['LS']:>7.2f}{x['LF']:>7.2f}{x['slack']:>8.2f}  {x['name']}{mark}")

    # критический путь: идём от конечной критической задачи назад по критическим предшественникам
    crit = []
    cur = max((t for t in T if abs(T[t]["slack"]) < 1e-9), key=lambda t: T[t]["EF"])
    while cur:
        crit.append(cur)
        prev = [d for d in T[cur]["deps"] if abs(T[d]["slack"]) < 1e-9 and abs(T[d]["EF"] - T[cur]["ES"]) < 1e-9]
        cur = prev[0] if prev else None
    crit.reverse()
    sigma = math.sqrt(sum(T[t]["s"] ** 2 for t in crit))
    print(f"\nКритический путь: {' -> '.join(crit)}")
    print(f"Ожидаемая длительность проекта: {finish:.2f}, σ = {sigma:.2f}")
    for p, z in ((50, 0), (85, 1.04), (90, 1.28), (95, 1.65)):
        print(f"  срок с вероятностью {p}%: {finish + z * sigma:.2f}")
    if a.deadline is not None:
        pr = phi((a.deadline - finish) / sigma) if sigma > 0 else float(a.deadline >= finish)
        print(f"Вероятность завершить к сроку {a.deadline:g}: {pr * 100:.1f}%")
    print("(* — задача на критическом пути; оценка вероятности учитывает только критический путь)")

    if a.mermaid:
        print("\n```mermaid\nflowchart LR")
        for t in order:
            print(f'    {t}["{t}: {T[t]["name"]}<br/>E={T[t]["E"]:.1f}, резерв={T[t]["slack"]:.1f}"]')
        for t in order:
            for d in T[t]["deps"]:
                arrow = "==>" if d in crit and t in crit else "-->"
                print(f"    {d} {arrow} {t}")
        print("    classDef crit fill:#F2A541,stroke:#0F3D3E;")
        print(f"    class {','.join(crit)} crit;\n```")


if __name__ == "__main__":
    main()
