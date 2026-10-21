#!/usr/bin/env python3
"""Метрики DORA и метрики потока по данным репозитория (ЛР 4).

Два режима:

1) Сбор из GitHub API и расчёт:
       export GITHUB_TOKEN=ghp_...            # токен с правом чтения репозитория
       python flow_metrics.py collect --repo owner/name --deploy-workflow deploy.yml --out data
       python flow_metrics.py report --data data --out docs/04-metrics

2) Только расчёт по CSV (GitLab, другой трекер, ручная выгрузка):
       python flow_metrics.py report --data data --out docs/04-metrics

Формат CSV в каталоге data (даты ISO 8601, например 2026-10-05T14:30:00Z):
  issues.csv       id,title,labels,created,started,done
                   labels через ';'; started — момент начала работы (пусто, если не начата);
                   done — момент завершения (пусто, если не завершена)
  prs.csv          id,title,created,first_commit,first_review,merged,size
  deployments.csv  id,time,status          status: success | failure

Соглашения проекта, на которые опирается расчёт:
  * начало работы над задачей — назначение исполнителя или метка --start-label
    (по умолчанию "in progress");
  * инцидент — задача с меткой "incident" (created — начало, done — восстановление);
  * развёртывание — успешный запуск workflow --deploy-workflow в основной ветке.

Графики строятся, если установлен matplotlib (pip install matplotlib).
"""
import argparse
import csv
import json
import os
import statistics
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

API = "https://api.github.com"


# ───────────────────────────── утилиты
def ts(s):
    if not s:
        return None
    s = s.strip().replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else ""


def days(td):
    return td.total_seconds() / 86400


def pct(vals, p):
    if not vals:
        return None
    v = sorted(vals)
    k = max(0, min(len(v) - 1, int(-(-p * len(v) // 100)) - 1))
    return v[k]


def fmt(x, unit="дн."):
    return "—" if x is None else f"{x:.1f} {unit}".strip()


# ───────────────────────────── сбор из GitHub
def gh(path, token, params=""):
    url = f"{API}{path}{'&' if '?' in path else '?'}per_page=100{params}"
    out = []
    while url:
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "Authorization": f"Bearer {token}", "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(req) as r:
            data = json.loads(r.read().decode())
            link = r.headers.get("Link", "")
        out.extend(data if isinstance(data, list) else data.get("workflow_runs", []))
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part[part.find("<") + 1:part.find(">")]
    return out


def collect(a):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("Задайте переменную окружения GITHUB_TOKEN")
    repo = a.repo
    os.makedirs(a.out, exist_ok=True)

    print("Задачи…")
    rows = []
    for it in gh(f"/repos/{repo}/issues?state=all", token):
        if "pull_request" in it:
            continue
        started = None
        for ev in gh(f"/repos/{repo}/issues/{it['number']}/events", token):
            is_start = ev["event"] == "assigned" or (ev["event"] == "labeled" and ev.get("label", {}).get("name", "").lower() == a.start_label.lower())
            if is_start:
                t = ts(ev["created_at"])
                started = t if started is None or t < started else started
        rows.append([it["number"], it["title"], ";".join(l["name"] for l in it["labels"]), it["created_at"], iso(started), it.get("closed_at") or ""])
    write(os.path.join(a.out, "issues.csv"), ["id", "title", "labels", "created", "started", "done"], rows)

    print("Pull request…")
    rows = []
    for pr in gh(f"/repos/{repo}/pulls?state=closed", token):
        if not pr.get("merged_at"):
            continue
        n = pr["number"]
        commits = gh(f"/repos/{repo}/pulls/{n}/commits", token)
        first_commit = min((ts(c["commit"]["author"]["date"]) for c in commits), default=None)
        reviews = gh(f"/repos/{repo}/pulls/{n}/reviews", token)
        first_review = min((ts(r["submitted_at"]) for r in reviews if r.get("submitted_at")), default=None)
        req = urllib.request.Request(f"{API}/repos/{repo}/pulls/{n}", headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req) as r:
            det = json.loads(r.read().decode())
        rows.append([n, pr["title"], pr["created_at"], iso(first_commit), iso(first_review), pr["merged_at"], det.get("additions", 0) + det.get("deletions", 0)])
    write(os.path.join(a.out, "prs.csv"), ["id", "title", "created", "first_commit", "first_review", "merged", "size"], rows)

    print("Развёртывания…")
    rows = []
    if a.deploy_workflow:
        for run in gh(f"/repos/{repo}/actions/workflows/{a.deploy_workflow}/runs?branch={a.branch}", token):
            if run["status"] != "completed" or run["conclusion"] not in ("success", "failure"):
                continue
            rows.append([run["id"], run["updated_at"], run["conclusion"]])
    write(os.path.join(a.out, "deployments.csv"), ["id", "time", "status"], rows)
    print(f"Данные сохранены в {a.out}")


def write(path, head, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(head)
        w.writerows(rows)


def read(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


# ───────────────────────────── расчёт
def dora_level(name, v):
    if v is None:
        return "—"
    if name == "df":  # развёртываний в неделю
        return "элитный" if v >= 7 else "высокий" if v >= 1 else "средний" if v >= 0.25 else "низкий"
    if name == "lt":  # дни
        return "элитный" if v < 1 else "высокий" if v <= 7 else "средний" if v <= 30 else "низкий"
    if name == "cfr":  # доля
        return "элитный" if v <= 0.15 else "высокий" if v <= 0.30 else "средний" if v <= 0.45 else "низкий"
    if name == "mttr":  # часы
        return "элитный" if v < 1 else "высокий" if v < 24 else "средний" if v < 24 * 7 else "низкий"


def report(a):
    issues = read(os.path.join(a.data, "issues.csv"))
    prs = read(os.path.join(a.data, "prs.csv"))
    deps = read(os.path.join(a.data, "deployments.csv"))
    os.makedirs(a.out, exist_ok=True)
    for i in issues:
        i["created"], i["started"], i["done"] = ts(i["created"]), ts(i.get("started")), ts(i.get("done"))
        i["labels"] = [x.strip().lower() for x in (i.get("labels") or "").split(";") if x.strip()]
    incidents = [i for i in issues if "incident" in i["labels"]]
    work = [i for i in issues if "incident" not in i["labels"]]

    # ── поток
    finished = [i for i in work if i["done"]]
    cycle = [days(i["done"] - (i["started"] or i["created"])) for i in finished]
    lead = [days(i["done"] - i["created"]) for i in finished]
    if not issues:
        sys.exit("Нет данных о задачах (issues.csv)")
    start = min(i["created"] for i in issues)
    end = max([i["done"] for i in issues if i["done"]] + [i["created"] for i in issues])
    week0 = (start - timedelta(days=start.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    nweeks = int(days(end - week0) // 7) + 1
    thr = [0] * nweeks
    for i in finished:
        thr[int(days(i["done"] - week0) // 7)] += 1
    write(os.path.join(a.out, "throughput_weekly.csv"), ["week_start", "throughput"], [[(week0 + timedelta(weeks=k)).date().isoformat(), thr[k]] for k in range(nweeks)])
    now = end
    wip_now = [i for i in work if i["started"] and not i["done"]]
    ages = [days(now - i["started"]) for i in wip_now]

    # ── DORA
    ok = sorted(ts(d["time"]) for d in deps if d["status"] == "success")
    failed = [d for d in deps if d["status"] == "failure"]
    period_w = max(days(end - start) / 7, 1 / 7)
    df = len(ok) / period_w if ok else None
    lt_changes = []
    for p in prs:
        m = ts(p.get("merged"))
        fc = ts(p.get("first_commit")) or ts(p.get("created"))
        if not m:
            continue
        nxt = next((d for d in ok if d >= m), None)
        if nxt:
            lt_changes.append(days(nxt - fc))
    cfr = (len(incidents) / len(ok)) if ok else None
    mttr = [days(i["done"] - i["created"]) * 24 for i in incidents if i["done"]]

    # ── pull request
    pr_size = [float(p["size"]) for p in prs if p.get("size")]
    to_review = [days(ts(p["first_review"]) - ts(p["created"])) * 24 for p in prs if p.get("first_review")]
    to_merge = [days(ts(p["merged"]) - ts(p["created"])) * 24 for p in prs if p.get("merged")]

    lt_med = statistics.median(lt_changes) if lt_changes else None
    mttr_med = statistics.median(mttr) if mttr else None
    md = []
    md.append("# Метрики процесса команды\n")
    md.append(f"Период: {start.date()} — {end.date()} ({period_w:.1f} нед.). Задач: {len(work)}, завершено: {len(finished)}; pull request: {len(prs)}; развёртываний: {len(ok)} успешных, {len(failed)} неуспешных; инцидентов: {len(incidents)}.\n")
    md.append("## Метрики DORA\n")
    md.append("| Метрика | Значение | Уровень |\n|---|---|---|")
    md.append(f"| Частота развёртываний | {'—' if df is None else f'{df:.2f} в неделю'} | {dora_level('df', df)} |")
    md.append(f"| Время выполнения изменений (медиана) | {fmt(lt_med)} | {dora_level('lt', lt_med)} |")
    md.append(f"| Доля неудачных изменений | {'—' if cfr is None else f'{cfr * 100:.0f}%'} | {dora_level('cfr', cfr)} |")
    md.append(f"| Время восстановления (медиана) | {fmt(mttr_med, 'ч')} | {dora_level('mttr', mttr_med)} |\n")
    md.append("## Метрики потока\n")
    md.append("| Метрика | p50 | p85 | p95 |\n|---|---|---|---|")
    md.append(f"| Время цикла задачи | {fmt(pct(cycle, 50))} | {fmt(pct(cycle, 85))} | {fmt(pct(cycle, 95))} |")
    md.append(f"| Время выполнения задачи (от создания) | {fmt(pct(lead, 50))} | {fmt(pct(lead, 85))} | {fmt(pct(lead, 95))} |")
    md.append(f"| Время до первого ревью PR | {fmt(pct(to_review, 50), 'ч')} | {fmt(pct(to_review, 85), 'ч')} | {fmt(pct(to_review, 95), 'ч')} |")
    md.append(f"| Время от открытия до слияния PR | {fmt(pct(to_merge, 50), 'ч')} | {fmt(pct(to_merge, 85), 'ч')} | {fmt(pct(to_merge, 95), 'ч')} |")
    md.append(f"| Размер PR, строк | {fmt(pct(pr_size, 50), '')} | {fmt(pct(pr_size, 85), '')} | {fmt(pct(pr_size, 95), '')} |\n")
    md.append(f"Пропускная способность по неделям: {thr} (среднее {statistics.mean(thr):.2f}). Файл throughput_weekly.csv можно передать в monte_carlo.py.\n")
    md.append(f"Незавершённая работа на конец периода: {len(wip_now)} задач; возраст: {', '.join(f'{x:.1f}' for x in sorted(ages, reverse=True)) or '—'} дн.\n")
    md.append(f"Соглашение об уровне обслуживания (SLE): 85% задач завершаются за {fmt(pct(cycle, 85))} или быстрее.\n")
    md.append("## Интерпретация\n\n_Заполняет команда: где узкое место, какие выбросы, что изменилось после экспериментов._\n")
    with open(os.path.join(a.out, "metrics_auto.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    print("\n".join(md))

    plots(a.out, issues, work, finished, cycle, thr, week0, start, end)


def plots(out, issues, work, finished, cycle, thr, week0, start, end):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
    except ImportError:
        print("\nmatplotlib не установлен — графики не построены (pip install matplotlib)")
        return
    teal, amber, sage, rust = "#0F6E6A", "#F2A541", "#9BB8B3", "#C8553D"

    # CFD
    day0 = start.replace(hour=0, minute=0, second=0, microsecond=0)
    xs, back, prog, done = [], [], [], []
    d = day0
    while d <= end + timedelta(days=1):
        xs.append(d)
        back.append(sum(1 for i in work if i["created"] <= d and not (i["started"] and i["started"] <= d) and not (i["done"] and i["done"] <= d)))
        prog.append(sum(1 for i in work if i["started"] and i["started"] <= d and not (i["done"] and i["done"] <= d)))
        done.append(sum(1 for i in work if i["done"] and i["done"] <= d))
        d += timedelta(days=1)
    fig, ax = plt.subplots(figsize=(9, 4.8))
    ax.stackplot(xs, done, prog, back, labels=["Готово", "В работе", "Бэклог"], colors=[teal, amber, sage])
    ax.set_title("Накопительная диаграмма потока (CFD)")
    ax.set_ylabel("Задач")
    ax.legend(loc="upper left", frameon=False)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "cfd.png"), dpi=150)

    # контрольная диаграмма
    if finished:
        fig, ax = plt.subplots(figsize=(9, 4.8))
        ax.scatter([i["done"] for i in finished], cycle, color=teal, s=36, zorder=3)
        for p, c in ((50, sage), (85, amber), (95, rust)):
            v = pct(cycle, p)
            ax.axhline(v, color=c, ls="--", lw=1.5, label=f"{p}% — {v:.1f} дн.")
        ax.set_title("Контрольная диаграмма времени цикла")
        ax.set_ylabel("Время цикла, дн.")
        ax.legend(frameon=False)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m"))
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        fig.savefig(os.path.join(out, "cycle_time.png"), dpi=150)

    # пропускная способность
    fig, ax = plt.subplots(figsize=(9, 4.2))
    labels = [(week0 + timedelta(weeks=k)).strftime("%d.%m") for k in range(len(thr))]
    ax.bar(labels, thr, color=teal)
    for k, v in enumerate(thr):
        ax.text(k, v + 0.05, str(v), ha="center", va="bottom", fontsize=9)
    ax.set_title("Пропускная способность по неделям")
    ax.set_ylabel("Завершено задач")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(os.path.join(out, "throughput.png"), dpi=150)
    print(f"\nГрафики сохранены в {out}: cfd.png, cycle_time.png, throughput.png")


def main():
    ap = argparse.ArgumentParser(description="Метрики DORA и потока")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="собрать данные из GitHub API в CSV")
    c.add_argument("--repo", required=True, help="owner/name")
    c.add_argument("--deploy-workflow", help="имя файла workflow развёртывания, например deploy.yml")
    c.add_argument("--branch", default="main")
    c.add_argument("--start-label", default="in progress")
    c.add_argument("--out", default="data")
    r = sub.add_parser("report", help="рассчитать метрики по CSV")
    r.add_argument("--data", default="data")
    r.add_argument("--out", default="docs/04-metrics")
    a = ap.parse_args()
    collect(a) if a.cmd == "collect" else report(a)


if __name__ == "__main__":
    main()
