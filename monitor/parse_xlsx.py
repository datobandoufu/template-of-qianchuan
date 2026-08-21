# -*- coding: utf-8 -*-
"""解析千川导出的 inlineStr 型 xlsx（天级新格式，15 列）。

背景：这批文件单元格用 t="inlineStr" 内联字符串存储，
openpyxl 读取会得到空表，因此直接解析 sheet XML。

新格式列（2026-08 起，按天维度导出）：
A 素材名称 / B 素材ID / C 素材评估 / D 素材时长 / E 素材创建时间 /
F 素材来源 / G 标签 / H 整体消耗 / I 净成交ROI / J 净成交金额 /
K 1小时内退款率 / L 整体支付ROI / M 整体成交金额 / N 净成交金额结算率 / O 净成交订单数
"""
import zipfile
import re
import hashlib
import xml.etree.ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

COL_MAP = {
    "A": "name",            # 素材名称
    "B": "mid",             # 素材ID
    "C": "evaluation",      # 素材评估
    "D": "duration",        # 素材时长
    "E": "created_at",      # 素材创建时间
    "F": "source",          # 素材来源
    "G": "tags",            # 标签
    "H": "spend_total",     # 整体消耗
    "I": "net_roi",         # 净成交ROI
    "J": "net_pay",         # 净成交金额
    "K": "refund_rate_1h",  # 1小时内退款率（"41.93%" 形式）
    "L": "roi",             # 整体支付ROI
    "M": "pay_total",       # 整体成交金额
    "N": "settle_rate",     # 净成交金额结算率（"100.00%" 形式）
    "O": "order_count",     # 净成交订单数
}


def _num(v):
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _pct(v):
    """百分比字符串（"41.93%"）转小数（0.4193）；已是数字则直接除以 100 前先判断。"""
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if s in ("", "-"):
        return None
    if s.endswith("%"):
        s = s[:-1]
        try:
            return float(s) / 100.0
        except ValueError:
            return None
    # 个别单元格可能是 0~1 小数或 0~100 数字，按原样返回数值（不做猜测换算）
    try:
        return float(s)
    except ValueError:
        return None


def _txt(v):
    if v is None:
        return None
    s = str(v).strip()
    return None if s in ("", "-") else s


def parse_rows(xlsx_path):
    """返回 (表头dict, 数据行列表)。每行是 列字母 -> 原始文本 的 dict。"""
    with zipfile.ZipFile(xlsx_path) as z:
        xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    root = ET.fromstring(xml)
    rows = []
    for row in root.iter(NS + "row"):
        cells = {}
        for c in row.iter(NS + "c"):
            ref = c.get("r")
            if not ref:
                continue
            col = re.match(r"([A-Z]+)", ref).group(1)
            isel = c.find(NS + "is")
            if isel is not None:
                cells[col] = "".join(t.text or "" for t in isel.iter(NS + "t"))
            else:
                vnode = c.find(NS + "v")
                cells[col] = vnode.text if vnode is not None and vnode.text is not None else None
        rows.append(cells)
    if not rows:
        return {}, []
    return rows[0], rows[1:]


def normalize_row(cells):
    """原始行 -> 语义化 dict：数值转 float，'-'/空 转 None。"""
    return {
        "name": _txt(cells.get("A")),
        "mid": _txt(cells.get("B")),
        "evaluation": _txt(cells.get("C")),
        "duration": _txt(cells.get("D")),
        "created_at": _txt(cells.get("E")),
        "source": _txt(cells.get("F")),
        "tags": _txt(cells.get("G")),
        "spend_total": _num(cells.get("H")),
        "net_roi": _num(cells.get("I")),
        "net_pay": _num(cells.get("J")),
        "refund_rate_1h": _pct(cells.get("K")),
        "roi": _num(cells.get("L")),
        "pay_total": _num(cells.get("M")),
        "settle_rate": _pct(cells.get("N")),
        "order_count": _num(cells.get("O")),
    }


def material_key(row):
    """素材唯一键：优先素材ID；缺失/为'-'时用名称哈希兜底。"""
    mid = (row.get("mid") or "").strip()
    if mid:
        return "id:" + mid
    name = (row.get("name") or "").strip()
    if name:
        h = hashlib.md5(name.encode("utf-8")).hexdigest()[:12]
        return "name:" + h
    return "unknown"


def is_aggregate_row(row):
    """AIGC 动态创意等聚合行：无素材ID 且名称为集合/汇总类。"""
    name = (row.get("name") or "").strip()
    return (not row.get("mid")) and ("集合" in name or "汇总" in name)
