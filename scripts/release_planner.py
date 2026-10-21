#!/usr/bin/env python3
"""Выбор состава релиза как задача о рюкзаке 0-1 с зависимостями (ЛР 1).

    max  sum v_i * x_i
    s.t. sum w_i * x_i <= W
         x_j <= x_i,      если история j зависит от i
         x_i = 1,         если история обязательная (must)
         x_i in {0, 1}

Точное решение — метод ветвей и границ (граница — релаксация линейного
программирования, т. е. дробный рюкзак). Для сравнения выводится жадное
решение по убыванию v/w (аналог WSJF).

Формат CSV (разделитель запятая, кодировка UTF-8):
    id,title,value,effort,depends_on,must
    US1,Регистрация,8,3,,1
    US2,Бронирование слота,13,5,US1,0
depends_on — список id через ';'; must — 1/0.

Запуск:
    python release_planner.py ../examples/backlog.csv --capacity 30
"""
import argparse
import csv
import sys


def load(path):
    items = []
    with open(path, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            items.append({
                "id": row["id"].strip(),
                "title": row.get("title", "").strip(),
                "v": float(row["value"]),
                "w": float(row["effort"]),
                "deps": [d.strip() for d in (row.get("depends_on") or "").split(";") if d.strip()],
                "must": (row.get("must") or "0").strip() in ("1", "true", "yes", "да"),
            })
    ids = {it["id"] for it in items}
    for it in items:
        for d in it["deps"]:
            if d not in ids:
                sys.exit(f"История {it['id']} зависит от неизвестной {d}")
    return items


def closure(items):
    """Для каждой истории — множество всех историй, от которых она зависит (транзитивно)."""
    by_id = {it["id"]: it for it in items}
    memo = {}

    def go(i, stack=()):
        if i in memo:
            return memo[i]
        if i in stack:
            sys.exit("Циклическая зависимость: " + " -> ".join(stack + (i,)))
        res = set()
        for d in by_id[i]["deps"]:
            res |= {d} | go(d, stack + (i,))
        memo[i] = res
        return res

    return {it["id"]: go(it["id"]) for it in items}


def feasible(sel, items, need, cap):
    by_id = {it["id"]: it for it in items}
    return sum(by_id[i]["w"] for i in sel) <= cap and all(need[i] <= sel for i in sel)


def greedy(items, need, cap):
    """Жадно по v/w; история берётся вместе со всеми её зависимостями, если помещается."""
    by_id = {it["id"]: it for it in items}
    sel = set()
    for it in items:
        if it["must"]:
            sel |= {it["id"]} | need[it["id"]]
    used = sum(by_id[i]["w"] for i in sel)
    for it in sorted(items, key=lambda x: x["v"] / x["w"], reverse=True):
        add = ({it["id"]} | need[it["id"]]) - sel
        cost = sum(by_id[i]["w"] for i in add)
        if add and used + cost <= cap:
            sel |= add
            used += cost
    return sel


def branch_and_bound(items, need, cap):
    by_id = {it["id"]: it for it in items}
    forced = set()
    for it in items:
        if it["must"]:
            forced |= {it["id"]} | need[it["id"]]
    base_w = sum(by_id[i]["w"] for i in forced)
    if base_w > cap:
        sys.exit(f"Обязательные истории ({base_w}) не помещаются в ёмкость {cap}")
    free = sorted([it for it in items if it["id"] not in forced], key=lambda x: x["v"] / x["w"], reverse=True)
    best = {"val": -1.0, "sel": set()}
    nodes = [0]

    def bound(k, w, v):
        # дробный рюкзак по оставшимся историям (зависимости ослаблены) — верхняя граница
        for it in free[k:]:
            if w + it["w"] <= cap:
                w += it["w"]
                v += it["v"]
            else:
                return v + it["v"] * (cap - w) / it["w"]
        return v

    def rec(k, sel, w, v):
        nodes[0] += 1
        if k == len(free):
            if v > best["val"] and all(need[i] <= sel for i in sel):
                best["val"], best["sel"] = v, set(sel)
            return
        if bound(k, w, v) <= best["val"] + 1e-9:
            return
        it = free[k]
        if w + it["w"] <= cap:
            sel.add(it["id"])
            rec(k + 1, sel, w + it["w"], v + it["v"])
            sel.discard(it["id"])
        rec(k + 1, sel, w, v)

    rec(0, set(forced), base_w, sum(by_id[i]["v"] for i in forced))
    return best["sel"], nodes[0]


def report(name, sel, items):
    by_id = {it["id"]: it for it in items}
    order = [it for it in items if it["id"] in sel]
    v = sum(it["v"] for it in order)
    w = sum(it["w"] for it in order)
    print(f"\n{name}: ценность = {v:g}, трудоёмкость = {w:g}, историй = {len(order)}")
    for it in order:
        tag = " [must]" if it["must"] else ""
        print(f"  {it['id']:<6} v={it['v']:<5g} w={it['w']:<5g} {it['title']}{tag}")
    return v


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("csv")
    ap.add_argument("--capacity", "-W", type=float, required=True, help="ёмкость команды на релиз (в тех же единицах, что effort)")
    a = ap.parse_args()
    items = load(a.csv)
    need = closure(items)
    g = greedy(items, need, a.capacity)
    opt, nodes = branch_and_bound(items, need, a.capacity)
    assert feasible(opt, items, need, a.capacity) and feasible(g, items, need, a.capacity)
    print(f"Историй в бэклоге: {len(items)}, ёмкость W = {a.capacity:g}")
    vg = report("Жадное решение (по убыванию v/w)", g, items)
    vo = report(f"Оптимальное решение (ветви и границы, узлов: {nodes})", opt, items)
    if vo > vg:
        print(f"\nОптимум лучше жадного на {vo - vg:g} ({(vo - vg) / vg * 100:.1f}%).")
        print("Только в жадном:", ", ".join(sorted(g - opt)) or "—", "| только в оптимуме:", ", ".join(sorted(opt - g)) or "—")
    else:
        print("\nЖадное решение совпало по ценности с оптимальным.")


if __name__ == "__main__":
    main()
