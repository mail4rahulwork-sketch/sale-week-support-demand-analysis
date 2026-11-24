"""Sale-week ticket wave: when do support tickets actually arrive after a big sale?

Simulated data only. Orders spike on sale day, but tickets arrive later and
change shape: payment/coupon issues first, then 'where is my order', then returns.
We compare two staffing plans for the 8 days after the sale.
"""
import math
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

os.makedirs("outputs", exist_ok=True)
rng = np.random.default_rng(42)
HIST = list(range(-12, 8))           # order history so normal days are steady
DAYS = list(range(-2, 8))            # 2 normal days before, sale day 0, 7 days after
BASE_ORDERS = 40_000
SALE_UPLIFT = {0: 3.0, 1: 1.6, 2: 1.2}  # orders x normal

# contact reasons: tickets per 100 orders, lag profile (share arriving on day d after order), AHT seconds
REASONS = {
    "Payment / coupon":   dict(rate=0.8, lag=[0.85, 0.15],                         aht=240),
    "Where is my order":  dict(rate=2.2, lag=[0.05, 0.25, 0.35, 0.20, 0.10, 0.05],  aht=300),
    "Returns / refunds":  dict(rate=1.1, lag=[0, 0, 0.05, 0.15, 0.25, 0.25, 0.2, 0.1], aht=480),
}

orders = {d: BASE_ORDERS * SALE_UPLIFT.get(d, 1.0) * rng.normal(1, 0.03) for d in HIST}

rows = []
for reason, p in REASONS.items():
    for d in DAYS:
        t = 0.0
        for od, o in orders.items():
            lag = d - od
            if 0 <= lag < len(p["lag"]):
                t += o * p["rate"] / 100 * p["lag"][lag]
        rows.append(dict(day=d, reason=reason, tickets=round(t), aht=p["aht"]))
df = pd.DataFrame(rows)
daily = df.pivot_table(index="day", columns="reason", values="tickets", aggfunc="sum")
daily["Total"] = daily.sum(axis=1)
daily["Orders"] = pd.Series({d: orders[d] for d in DAYS}).round()
daily["Tickets per 100 orders"] = (daily["Total"] / daily["Orders"] * 100).round(2)
work_hours = df.assign(h=df.tickets * df.aht / 3600).groupby("day").h.sum()
daily["Workload hours"] = work_hours.round(0)

# staffing: productive hours per agent per day = 8h * (1 - 30% shrinkage) * 85% occupancy
HRS_PER_AGENT = 8 * 0.70 * 0.85
need = (daily["Workload hours"] / HRS_PER_AGENT).apply(math.ceil)
normal = int(need.loc[-1])
# Plan A: staff for the order spike (big extra batch on day 0 only, +50% on day 1, back to normal after)
plan_a = {d: normal for d in DAYS}
plan_a[0] = int(normal * 2.0); plan_a[1] = int(normal * 1.5)
# Plan B: same total extra agent-days, shifted to follow the ticket wave
extra = sum(plan_a[d] - normal for d in DAYS)
gap = {d: max(0, need[d] - normal) for d in DAYS}
tot = sum(gap.values()) or 1
plan_b = {d: normal + round(extra * gap[d] / tot) for d in DAYS}

daily["Agents needed"] = need
daily["Plan A: staff the sale day"] = pd.Series(plan_a)
daily["Plan B: staff the wave"] = pd.Series(plan_b)
for k, plan in (("A", plan_a), ("B", plan_b)):
    daily[f"Backlog hours {k}"] = 0.0
    backlog = 0.0
    for d in DAYS:
        cap = plan[d] * HRS_PER_AGENT
        backlog = max(0.0, backlog + daily.loc[d, "Workload hours"] - cap)
        daily.loc[d, f"Backlog hours {k}"] = round(backlog, 0)

daily.index.name = "Day vs sale"
daily.to_csv("outputs/sale_week_plan.csv")

peak_day = int(daily["Total"].idxmax())
summary = {
    "orders_peak_day": int(daily["Orders"].idxmax()),
    "tickets_peak_day": peak_day,
    "tickets_sale_day": int(daily.loc[0, "Total"]),
    "tickets_peak": int(daily["Total"].max()),
    "agents_normal": normal,
    "extra_agent_days": int(extra),
    "worst_backlog_A": int(daily["Backlog hours A"].max()),
    "worst_backlog_B": int(daily["Backlog hours B"].max()),
    "backlog_end_A": int(daily.loc[7, "Backlog hours A"]),
    "backlog_end_B": int(daily.loc[7, "Backlog hours B"]),
}
pd.Series(summary).to_csv("outputs/summary.csv", header=["value"])

# chart
fig, ax = plt.subplots(1, 2, figsize=(13, 4.6))
x = daily.index
ax[0].plot(x, daily["Orders"] / 1000, color="#94a3b8", lw=2, label="Orders (thousands)")
ax2 = ax[0].twinx()
bottom = np.zeros(len(x))
colors = {"Payment / coupon": "#f59e0b", "Where is my order": "#2563eb", "Returns / refunds": "#7c3aed"}
for r, c in colors.items():
    ax2.bar(x, daily[r], bottom=bottom, color=c, alpha=0.85, label=r, width=0.7)
    bottom += daily[r].values
ax[0].set_title("Orders peak on sale day. Tickets peak later.", loc="left", fontsize=11)
ax[0].set_xlabel("Day vs sale (0 = sale day)"); ax[0].set_ylabel("Orders (000)"); ax2.set_ylabel("Tickets")
h1, l1 = ax[0].get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax[0].legend(h1 + h2, l1 + l2, fontsize=8, loc="upper right", frameon=False)
ax[1].plot(x, daily["Agents needed"], color="#111827", lw=2.2, label="Agents needed")
ax[1].plot(x, daily["Plan A: staff the sale day"], color="#ef4444", lw=1.8, ls="--", label="Plan A: staff the sale day")
ax[1].plot(x, daily["Plan B: staff the wave"], color="#16a34a", lw=1.8, ls="--", label="Plan B: same extra people, moved to the wave")
ax[1].set_title("Same extra agent-days, very different result", loc="left", fontsize=11)
ax[1].set_xlabel("Day vs sale"); ax[1].set_ylabel("Agents"); ax[1].legend(fontsize=8, frameon=False)
for a in (ax[0], ax[1]): a.spines[["top", "right"]].set_visible(False)
fig.text(0.01, 0.01, "Simulated data. github.com/mail4rahulwork-sketch", fontsize=8, color="#6b7280")
fig.tight_layout(rect=(0, 0.03, 1, 1))
fig.savefig("outputs/sale_week_wave.png", dpi=100)
print(daily[["Orders", "Total", "Tickets per 100 orders", "Agents needed", "Plan A: staff the sale day", "Plan B: staff the wave", "Backlog hours A", "Backlog hours B"]].to_string())
print(summary)
