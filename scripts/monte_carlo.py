#!/usr/bin/env python3
"""Вероятностный прогноз срока выполнения бэклога методом Монте-Карло (ЛР 1, ЛР 4).

История пропускной способности задаётся списком (число задач, завершённых
за каждую неделю или день) либо CSV-файлом с колонкой throughput
(такой файл создаёт flow_metrics.py: throughput_weekly.csv).

Запуск:
    python monte_carlo.py --history 3 5 2 4 6 3 4 5 --backlog 40
    python monte_carlo.py --csv throughput_weekly.csv --backlog 25 --plot forecast.png
"""
import argparse
import csv
import math
import random
from collections import Counter


def simulate(history, backlog, runs, seed):
    rnd = random.Random(seed)
    if not any(history):
        raise SystemExit("В истории нет ни одного периода с завершёнными задачами")
    res = []
    for _ in range(runs):
        done, periods = 0, 0
        while done < backlog:
            done += rnd.choice(history)
            periods += 1
        res.append(periods)
    return sorted(res)


def percentile(sorted_vals, p):
    k = max(0, min(len(sorted_vals) - 1, math.ceil(p / 100 * len(sorted_vals)) - 1))
    return sorted_vals[k]


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--history", type=int, nargs="+", help="пропускная способность по периодам")
    g.add_argument("--csv", help="CSV с колонкой throughput")
    ap.add_argument("--backlog", type=int, required=True, help="число оставшихся задач")
    ap.add_argument("--runs", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--unit", default="нед.", help="единица периода в выводе")
    ap.add_argument("--plot", help="сохранить гистограмму в PNG (нужен matplotlib)")
    a = ap.parse_args()
    if a.csv:
        with open(a.csv, encoding="utf-8-sig") as f:
            history = [int(float(r["throughput"])) for r in csv.DictReader(f)]
    else:
        history = a.history
    res = simulate(history, a.backlog, a.runs, a.seed)
    print(f"История ({len(history)} периодов): {history}; среднее {sum(history) / len(history):.2f}")
    print(f"Бэклог: {a.backlog} задач, симуляций: {a.runs}\n")
    cnt = Counter(res)
    cum = 0
    print(f"{'Периодов':>9}  {'Доля':>6}  {'Накоп.':>6}")
    for k in sorted(cnt):
        cum += cnt[k]
        print(f"{k:>9}  {cnt[k] / a.runs * 100:>5.1f}%  {cum / a.runs * 100:>5.1f}%  {'#' * int(cnt[k] / a.runs * 100)}")
    print()
    for p in (50, 70, 85, 95):
        print(f"С вероятностью {p}% бэклог будет выполнен не позже чем за {percentile(res, p)} {a.unit}")

    if a.plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            raise SystemExit("Для --plot установите matplotlib: pip install matplotlib")
        xs = sorted(cnt)
        fig, ax = plt.subplots(figsize=(8, 4.5))
        ax.bar(xs, [cnt[x] / a.runs * 100 for x in xs], color="#0F6E6A")
        for p, c in ((50, "#6C8F8B"), (85, "#F2A541"), (95, "#C8553D")):
            v = percentile(res, p)
            ax.axvline(v, color=c, ls="--", lw=2, label=f"{p}% — {v} {a.unit}")
        ax.set_xlabel(f"Число периодов ({a.unit})")
        ax.set_ylabel("Доля симуляций, %")
        ax.set_title(f"Монте-Карло: {a.backlog} задач, {a.runs} симуляций")
        ax.legend(frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(a.plot, dpi=150)
        print(f"\nГрафик сохранён: {a.plot}")


if __name__ == "__main__":
    main()
