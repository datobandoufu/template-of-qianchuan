# -*- coding: utf-8 -*-
"""生成本地网页看板：output/dashboard/（index.html + data_<账户>.js）。

多账户架构（2026-08-20 起）：
- 每个账户独立生成数据文件 data_<hash>.js（window.DASH_DATA = {...}）；
- 默认账户数据内嵌进 index.html（保持首屏自包含），另存 data.js 供外部工具检视；
- index.html 顶部注入账户列表（ACCOUNTS），前端通过「?account=账户」切换加载。

数据源为天级（daily_stats），页面数据为 ISO 自然周聚合结果。
静态站点，无后端依赖；通过 启动看板.bat 起本地服务访问。
"""
import os
import sys
import json
import hashlib
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_conn, DEFAULT_ACCOUNT
from accounts import discover_accounts, account_has_data
from metrics import (load_all, weekly_trend, source_structure, material_cards,
                     new_week_report, get_week_end_map)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "output", "dashboard")
TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates", "index.html")


def data_file_for(account):
    """账户 -> 数据文件名（避免中文/特殊字符文件名问题，用哈希短码）。"""
    h = hashlib.sha1(account.encode("utf-8")).hexdigest()[:10]
    return f"data_{h}.js"


def build_data(account):
    """为指定账户构建看板数据（结构与原单账户完全一致）。"""
    weeks, mats, stats = load_all(account)
    cards = material_cards(weeks, mats, stats)
    cards_by_key = {c["key"]: c for c in cards}

    # 注入天级明细 days：供前端按任意时间区间（起止日期）圈选聚合。
    # days 每项为紧凑数组 [日期, 整体消耗, 整体成交金额, 净成交金额, 净成交订单数, 1小时退款率, 结算率]
    # （退款率/结算率为 0~1 小数，由前端按对应成交金额加权聚合）
    conn = get_conn(account)
    day_rows = conn.execute(
        "SELECT material_key, period_start, spend_total, pay_total, net_pay,"
        " order_count, refund_rate_1h, settle_rate FROM daily_stats"
        " ORDER BY material_key, period_start").fetchall()
    days_by_key = {}
    for r in day_rows:
        days_by_key.setdefault(r["material_key"], []).append([
            r["period_start"],
            round(r["spend_total"] or 0, 2),
            round(r["pay_total"] or 0, 2),
            round(r["net_pay"] or 0, 2),
            round(r["order_count"] or 0, 2),
            r["refund_rate_1h"] if r["refund_rate_1h"] is not None else None,
            r["settle_rate"] if r["settle_rate"] is not None else None,
        ])
    for c in cards:
        c["days"] = days_by_key.get(c["key"], [])
    day_min = min((d[0] for c in cards for d in c["days"]), default="")
    day_max = max((d[0] for c in cards for d in c["days"]), default="")

    created_report, firstseen_report = new_week_report(weeks, mats, stats, cards_by_key)
    revisions = [dict(r) for r in conn.execute(
        "SELECT rl.*, m.name FROM revision_log rl LEFT JOIN materials m"
        " ON m.material_key=rl.material_key ORDER BY rl.id")]
    conn.close()

    week_end_map = get_week_end_map(account)
    trend = weekly_trend(stats, weeks)
    data = {
        "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "account": account,
        "weeks": weeks,
        "week_ends": [week_end_map.get(w, w) for w in weeks],
        "day_min": day_min,
        "day_max": day_max,
        "trend": trend,
        "sources": source_structure(stats),
        "top10": [{
            "name": c["name"], "mid": c["mid"], "source": c["source"],
            "total_spend": c["total_spend"], "total_pay": c["total_pay"],
            "total_net_pay": c["total_net_pay"], "total_roi": c["total_roi"],
            "total_net_roi": c["total_net_roi"], "is_aggregate": c["is_aggregate"],
        } for c in cards[:10]],
        "materials": cards,
        "new_created": created_report,
        "new_firstseen": firstseen_report,
        "revisions": revisions,
        "totals": {
            "spend": round(sum(t["spend"] for t in trend), 2),
            "pay": round(sum(t["pay"] for t in trend), 2),
            "net_pay": round(sum(t["net_pay"] for t in trend), 2),
            "order_count": round(sum(t["order_count"] for t in trend), 2),
            "material_count": len(mats),
            "week_count": len(weeks),
        },
    }
    return data


def json_body(data):
    """转 JSON，并转义 </ 防止截断 HTML 解析。"""
    json_str = json.dumps(data, ensure_ascii=False)
    return json_str.replace("</", "<\\/")


def generate_dashboard():
    os.makedirs(OUT_DIR, exist_ok=True)

    accounts = discover_accounts()
    has_data = [a for a in accounts if account_has_data(a)]
    if not has_data:
        print("  警告：当前没有任何账户有入库数据，看板将仅展示账户切换列表。")

    # 1) 每个有数据的账户生成独立数据文件 data_<hash>.js
    for acc in has_data:
        data = build_data(acc)
        js = "window.DASH_DATA = " + json_body(data) + ";"
        path = os.path.join(OUT_DIR, data_file_for(acc))
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(js)
        print(f"  账户数据: {path}（{len(js)//1024} KB）")

    # 2) 默认账户数据内嵌进 index.html（保持首屏自包含单文件体验）
    if DEFAULT_ACCOUNT in has_data:
        default_data = build_data(DEFAULT_ACCOUNT)
    else:
        default_data = {
            "generated_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "account": DEFAULT_ACCOUNT, "weeks": [], "week_ends": [],
            "day_min": "", "day_max": "", "trend": [], "sources": [], "top10": [],
            "materials": [], "new_created": [], "new_firstseen": [],
            "revisions": [], "totals": {"spend": 0, "pay": 0, "net_pay": 0,
                                        "order_count": 0, "material_count": 0, "week_count": 0},
        }

    accounts_meta = [
        {"id": a, "file": data_file_for(a), "has_data": a in has_data}
        for a in accounts
    ]

    with open(TEMPLATE, encoding="utf-8") as fh:
        html = fh.read()
    html = html.replace("/*__DASH_DATA__*/",
                        "window.DASH_DATA = " + json_body(default_data) + ";")
    accounts_js = json_body({
        "embedded": DEFAULT_ACCOUNT,
        "list": accounts_meta,
    })
    html = html.replace("/*__ACCOUNTS__*/",
                        "const EMBEDDED_ACCOUNT = ACCT_EMBEDDED.embedded;\n"
                        "const ACCOUNTS = ACCT_EMBEDDED.list;")
    html = html.replace("/*__ACCOUNTS_META__*/",
                        "const ACCT_EMBEDDED = " + accounts_js + ";")
    html_path = os.path.join(OUT_DIR, "index.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(html)
    print(f"  网页看板已生成: {html_path}（自包含，{len(html)//1024} KB）")

    # 3) 另存默认账户 data.js 供人工检视/外部工具使用（页面本身不再依赖它）
    data_path = os.path.join(OUT_DIR, "data.js")
    with open(data_path, "w", encoding="utf-8") as fh:
        fh.write("window.DASH_DATA = ")
        fh.write(json_body(default_data))
        fh.write(";")


if __name__ == "__main__":
    generate_dashboard()
