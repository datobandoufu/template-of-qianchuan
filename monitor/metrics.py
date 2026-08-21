# -*- coding: utf-8 -*-
"""派生指标引擎：天级数据加载 -> ISO 自然周聚合，周趋势、素材序列、阶段标签、
预警、新增双口径、次周留存。

口径（2026-08 起）：
- 数据源为天级（daily_stats），报表统一按 ISO 自然周（周一~周日）聚合。
- 金额类求和；整体支付ROI = 整体成交金额÷整体消耗；净成交ROI = 净成交金额÷整体消耗；
  1小时内退款率按「整体成交金额」加权；净成交金额结算率按「净成交金额」加权。
"""
import os
import re
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import get_conn


def week_start_of(day):
    """ISO 自然周（周一~周日）起始日。"""
    d = datetime.date.fromisoformat(day)
    return (d - datetime.timedelta(days=d.weekday())).isoformat()


def week_end_of(week_start):
    """周起始日 -> 周结束日（起始日+6）。"""
    d = datetime.date.fromisoformat(week_start)
    return (d + datetime.timedelta(days=6)).isoformat()


def load_all(account=None):
    """加载指定账户的全量数据（缺省为默认账户）。返回 (weeks, mats, stats)。
    weeks: 按时间升序的 ISO 周起始日列表
    mats:  {material_key: 素材主档 dict}
    stats: 天级事实聚合为周后的 dict 列表（含 _m 引用素材主档）
    """
    conn = get_conn(account)
    days = [r["period_start"] for r in conn.execute(
        "SELECT DISTINCT period_start FROM daily_stats ORDER BY period_start")]
    mats = {r["material_key"]: dict(r) for r in conn.execute("SELECT * FROM materials")}
    daily = []
    for r in conn.execute("SELECT * FROM daily_stats ORDER BY period_start"):
        daily.append(dict(r))
    conn.close()
    weeks = sorted(set(week_start_of(d) for d in days))
    stats = aggregate_to_weeks(daily)
    for s in stats:
        s["_m"] = mats.get(s["material_key"], {})
    return weeks, mats, stats


def aggregate_to_weeks(daily):
    """天级事实 -> 周级事实（按 material_key + ISO 周起始日）。"""
    buckets = {}
    for s in daily:
        wk = week_start_of(s["period_start"])
        key = (s["material_key"], wk)
        a = buckets.get(key)
        if a is None:
            a = {
                "material_key": s["material_key"],
                "period_start": wk,
                "period_end": week_end_of(wk),
                "evaluation": s.get("evaluation"),
                "source": s.get("source"),
                "spend_total": 0.0,   # 整体消耗
                "net_pay": 0.0,       # 净成交金额
                "pay_total": 0.0,     # 整体成交金额
                "order_count": 0.0,   # 净成交订单数
                "_refund_num": 0.0,   # 退款率加权分子 = Σ(退款率×整体成交金额)
                "_refund_den": 0.0,   # 退款率加权分母 = Σ 整体成交金额
                "_settle_num": 0.0,   # 结算率加权分子 = Σ(结算率×净成交金额)
                "_settle_den": 0.0,   # 结算率加权分母 = Σ 净成交金额
                "_last_day": s["period_start"],
            }
            buckets[key] = a
        a["spend_total"] += s["spend_total"] or 0
        a["net_pay"] += s["net_pay"] or 0
        a["pay_total"] += s["pay_total"] or 0
        a["order_count"] += s["order_count"] or 0
        a["_refund_num"] += (s["refund_rate_1h"] or 0) * (s["pay_total"] or 0)
        a["_refund_den"] += s["pay_total"] or 0
        a["_settle_num"] += (s["settle_rate"] or 0) * (s["net_pay"] or 0)
        a["_settle_den"] += s["net_pay"] or 0
        # 评估/来源取该周最晚一天
        if s["period_start"] > a["_last_day"]:
            a["_last_day"] = s["period_start"]
            a["evaluation"] = s.get("evaluation")
            a["source"] = s.get("source")

    stats = []
    for a in buckets.values():
        spend = a["spend_total"]
        a["roi"] = round(a["pay_total"] / spend, 6) if spend else None
        a["net_roi"] = round(a["net_pay"] / spend, 6) if spend else None
        a["refund_rate_1h"] = round(a["_refund_num"] / a["_refund_den"], 6) if a["_refund_den"] else None
        a["settle_rate"] = round(a["_settle_num"] / a["_settle_den"], 6) if a["_settle_den"] else None
        for k in ("_refund_num", "_refund_den", "_settle_num", "_settle_den", "_last_day"):
            a.pop(k, None)
        stats.append(a)
    stats.sort(key=lambda s: s["period_start"])
    return stats


def get_week_end_map(account=None):
    """周起始日 -> 周结束日 映射（用于展示"从几号到几号"）。"""
    conn = get_conn(account)
    out = {}
    for r in conn.execute("SELECT DISTINCT period_start FROM daily_stats"):
        out[week_start_of(r["period_start"])] = week_end_of(week_start_of(r["period_start"]))
    conn.close()
    return out


def weekly_trend(stats, weeks):
    """每周汇总：素材数、消耗、整体成交金额、净成交、ROI、订单、退款率、结算率，含环比。"""
    rows = []
    for wk in weeks:
        ws = [s for s in stats if s["period_start"] == wk]
        spend = sum(s["spend_total"] or 0 for s in ws)
        pay = sum(s["pay_total"] or 0 for s in ws)
        net_pay = sum(s["net_pay"] or 0 for s in ws)
        order = sum(s["order_count"] or 0 for s in ws)
        refund_den = sum(s["pay_total"] or 0 for s in ws)
        refund_num = sum((s["refund_rate_1h"] or 0) * (s["pay_total"] or 0) for s in ws)
        settle_den = sum(s["net_pay"] or 0 for s in ws)
        settle_num = sum((s["settle_rate"] or 0) * (s["net_pay"] or 0) for s in ws)
        rows.append({
            "week": wk,
            "count": len(ws),
            "spend": round(spend, 2),
            "pay": round(pay, 2),           # 整体成交金额
            "roi": round(pay / spend, 2) if spend else 0,
            "net_pay": round(net_pay, 2),
            "net_roi": round(net_pay / spend, 2) if spend else 0,
            "order_count": round(order, 2),
            # 退款率/结算率为 0~1 比率：保留 4 位（对应百分比展示两位小数，如 3.19%）
            "refund_rate_1h": round(refund_num / refund_den, 4) if refund_den else None,
            "settle_rate": round(settle_num / settle_den, 4) if settle_den else None,
        })
    for i in range(1, len(rows)):
        prev = rows[i - 1]
        cur = rows[i]
        # 环比为比率：保留 4 位（对应百分比展示两位小数，如 12.34%）
        cur["spend_delta"] = round(cur["spend"] / prev["spend"] - 1, 4) if prev["spend"] else None
        cur["pay_delta"] = round(cur["pay"] / prev["pay"] - 1, 4) if prev["pay"] else None
        cur["roi_delta"] = round(cur["roi"] / prev["roi"] - 1, 4) if prev["roi"] else None
        cur["net_roi_delta"] = round(cur["net_roi"] / prev["net_roi"] - 1, 4) if prev["net_roi"] else None
    return rows


def source_structure(stats):
    """素材来源结构：条数、消耗、整体成交金额、占比。"""
    agg = {}
    for s in stats:
        src = s["source"] or "未知"
        a = agg.setdefault(src, {"count": 0, "spend": 0.0, "pay": 0.0})
        a["count"] += 1
        a["spend"] += s["spend_total"] or 0
        a["pay"] += s["pay_total"] or 0
    total = sum(a["spend"] for a in agg.values()) or 1
    out = []
    for src, a in sorted(agg.items(), key=lambda kv: -kv[1]["spend"]):
        out.append({
            "source": src, "count": a["count"],
            "spend": round(a["spend"], 2), "pay": round(a["pay"], 2),
            "ratio": round(a["spend"] / total, 4),
        })
    return out


def material_series(stats, key):
    return [s for s in stats if s["material_key"] == key]


def phase_label(series):
    """根据最近几周消耗走势给阶段标签。"""
    spend_seq = [s["spend_total"] or 0 for s in series]
    if not spend_seq:
        return "未投放"
    if len(spend_seq) == 1:
        return "🆕新素材" if spend_seq[-1] > 0 else "未投放"
    if spend_seq[-1] == 0 and sum(spend_seq[:-1]) > 0:
        return "⏸️停投"
    if len(spend_seq) >= 3:
        last3 = spend_seq[-3:]
        if last3[-1] > last3[-2] > last3[-3]:
            return "📈放量中"
        if 0 < last3[-1] < last3[-2] < last3[-3]:
            return "📉衰退"
    return "稳定"


def warning_flags(m, series):
    """预警：ROI<1 / 消耗单周骤降>50% / 同质化。"""
    flags = []
    if not series:
        return flags
    last = series[-1]
    if last["roi"] is not None and last["roi"] < 1.0 and (last["spend_total"] or 0) > 0:
        flags.append("ROI<1")
    if len(series) >= 2:
        prev = series[-2]["spend_total"] or 0
        cur = last["spend_total"] or 0
        if prev > 0 and cur < prev * 0.5:
            flags.append("消耗骤降>50%")
    if (m.get("latest_evaluation") or "") == "同质化":
        flags.append("同质化")
    return flags


def new_by_created(mats, week_start, week_end):
    """口径A：素材创建时间落在该周（真实上新节奏）。"""
    out = []
    for m in mats.values():
        ct = m.get("created_at") or ""
        if re.match(r"^\d{4}-\d{2}-\d{2}", ct) and week_start <= ct[:10] <= week_end:
            out.append(m)
    return sorted(out, key=lambda m: m.get("created_at") or "")


def new_by_first_seen(mats, week_start):
    """口径B：首次出现在周报中的那一周（由首见天归属到周）。"""
    out = []
    for m in mats.values():
        d = m.get("first_seen_day") or ""
        try:
            if week_start_of(d) == week_start:
                out.append(m)
        except (ValueError, TypeError):
            continue
    return sorted(out, key=lambda m: m.get("created_at") or "")


def retention(stats, key, week_start, weeks):
    """次周留存：返回 (是否继续投放, 次周消耗, 次周ROI)；无次周数据返回 None。"""
    if week_start not in weeks:
        return None
    idx = weeks.index(week_start)
    if idx + 1 >= len(weeks):
        return None
    nxt = weeks[idx + 1]
    rows = [s for s in stats if s["material_key"] == key and s["period_start"] == nxt]
    if not rows:
        return None
    r = rows[0]
    return (bool(r["spend_total"]), r["spend_total"] or 0, r["roi"])


def material_cards(weeks, mats, stats):
    """每个素材一张汇总卡：累计、最新周、环比、阶段、预警，含新指标。"""
    cards = []
    for key, m in mats.items():
        series = material_series(stats, key)
        if not series:
            continue
        tot_spend = sum(s["spend_total"] or 0 for s in series)
        tot_pay = sum(s["pay_total"] or 0 for s in series)
        tot_net_pay = sum(s["net_pay"] or 0 for s in series)
        tot_order = sum(s["order_count"] or 0 for s in series)
        last = series[-1]
        prev = series[-2] if len(series) >= 2 else None
        card = {
            "key": key,
            "name": m.get("name") or "",
            "mid": m.get("material_id") or "",
            "source": m.get("source") or "",
            "duration": m.get("duration") or "",
            "created_at": m.get("created_at") or "",
            "first_seen": m.get("first_seen_day") or "",
            "evaluation": m.get("latest_evaluation") or "",
            "is_aggregate": m.get("is_aggregate") or 0,
            # 名称拆解归属字段
            "channel": m.get("channel") or "",
            "product": m.get("product") or "",
            "product_raw": m.get("product_raw") or "",
            "material_no": m.get("material_no") or "",
            "created_date": m.get("created_date") or "",
            "author": m.get("author") or "",
            "mix_author": m.get("mix_author") or "",
            "parse_status": m.get("parse_status") or "ok",
            "is_ai": 1 if m.get("is_ai") else 0,
            "ai_tag": m.get("ai_tag") or "",
            "active_weeks": len(series),
            "phase": phase_label(series),
            "flags": warning_flags(m, series),
            "total_spend": round(tot_spend, 2),
            "total_pay": round(tot_pay, 2),           # 整体成交金额
            "total_net_pay": round(tot_net_pay, 2),
            "total_order_count": round(tot_order, 2),
            "total_roi": round(tot_pay / tot_spend, 2) if tot_spend else 0,
            "total_net_roi": round(tot_net_pay / tot_spend, 2) if tot_spend else 0,
            "last_week": last["period_start"],
            "last_spend": round(last["spend_total"] or 0, 2),
            "last_pay": round(last["pay_total"] or 0, 2),
            "last_net_pay": round(last["net_pay"] or 0, 2),
            "last_order_count": round(last["order_count"] or 0, 2),
            "last_roi": round(last["roi"], 2) if last["roi"] is not None else None,
            "last_net_roi": round(last["net_roi"], 2) if last["net_roi"] is not None else None,
            "last_refund_rate_1h": round(last["refund_rate_1h"], 4) if last["refund_rate_1h"] is not None else None,
            "last_settle_rate": round(last["settle_rate"], 4) if last["settle_rate"] is not None else None,
            "spend_delta": None, "pay_delta": None, "roi_delta": None,
            "series": [{
                "week": s["period_start"],
                "spend": round(s["spend_total"] or 0, 2),
                "pay": round(s["pay_total"] or 0, 2),
                "net_pay": round(s["net_pay"] or 0, 2),
                "roi": round(s["roi"], 2) if s["roi"] is not None else None,
                "net_roi": round(s["net_roi"], 2) if s["net_roi"] is not None else None,
                "order_count": round(s["order_count"] or 0, 2),
                "refund_rate_1h": round(s["refund_rate_1h"], 4) if s["refund_rate_1h"] is not None else None,
                "settle_rate": round(s["settle_rate"], 4) if s["settle_rate"] is not None else None,
                "evaluation": s["evaluation"] or "",
            } for s in series],
        }
        if prev is not None:
            card["spend_delta"] = round(card["last_spend"] / (prev["spend_total"] or 0) - 1, 4) if prev["spend_total"] else None
            card["pay_delta"] = round(card["last_pay"] / (prev["pay_total"] or 0) - 1, 4) if prev["pay_total"] else None
            if prev["roi"] and last["roi"] is not None:
                card["roi_delta"] = round(last["roi"] / prev["roi"] - 1, 4)
        cards.append(card)
    cards.sort(key=lambda c: -c["total_spend"])
    return cards


def new_week_report(weeks, mats, stats, cards_by_key):
    """新增素材周报（双口径），带首周表现与次周留存。"""
    created_report = []
    for wk in weeks:
        wk_end = week_end_of(wk)
        items = []
        for m in new_by_created(mats, wk, wk_end):
            key = m["material_key"]
            card = cards_by_key.get(key)
            first = card["series"][0] if card else None
            rt = retention(stats, key, wk, weeks)
            items.append({
                "key": key,
                "name": m.get("name") or "", "mid": m.get("material_id") or "",
                "created_at": m.get("created_at") or "",
                "first_spend": (first["spend"] if first else 0),
                "first_roi": (first["roi"] if first else None),
                "keep": bool(rt[0]) if rt else None,
                "next_spend": rt[1] if rt else None,
                "next_roi": rt[2] if rt else None,
            })
        created_report.append({"week": wk, "items": items})

    firstseen_report = []
    for wk in weeks:
        items = []
        for m in new_by_first_seen(mats, wk):
            key = m["material_key"]
            card = cards_by_key.get(key)
            first = card["series"][0] if card else None
            rt = retention(stats, key, wk, weeks)
            items.append({
                "key": key,
                "name": m.get("name") or "", "mid": m.get("material_id") or "",
                "created_at": m.get("created_at") or "",
                "first_spend": (first["spend"] if first else 0),
                "first_roi": (first["roi"] if first else None),
                "keep": bool(rt[0]) if rt else None,
                "next_spend": rt[1] if rt else None,
                "next_roi": rt[2] if rt else None,
            })
        firstseen_report.append({"week": wk, "items": items})
    return created_report, firstseen_report
