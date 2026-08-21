# -*- coding: utf-8 -*-
"""生成示例日报数据（通用模板演示 / 预览用）。

在项目根目录创建「示例账户-直播」文件夹，生成若干天的天级日报 xlsx
（文件名含单日周期，15 列 inlineStr 格式，与官方导出格式一致），
数据为程序随机生成、完全虚构，不含任何真实业务信息。

用法：
    python monitor/generate_sample_data.py
    生成后导入：python monitor/import_daily.py --account 示例账户-直播
    或直接双击 一键导入.bat（会自动扫描到示例账户）

演示场景覆盖：
- 渠道：直播 / 种草 / 混剪 / 素材采买 / 即梦AI；
- AI 素材识别：即梦AI 素材（平台AI裂变）+【AI】方括号标识素材（素材1009）；
- 阶段：新素材（素材1007 窗口末上新） / 放量中（素材1008 末周仍上升） /
  稳定 / 衰退 / 停投（素材1006 活跃两周后停投，停投期仍出现在报表且消耗为 0）；
- 预警：同质化（大规格包装素材 / 即梦AI 素材）；
- 聚合行：AIGC动态创意视频素材集合（无 ID，不参与单素材去重）；
- 产品规格归并：示例产品-2kg → 示例产品（name_parser 归一化）。

重置为空白模板：删除「示例账户-直播」文件夹及 data/、output/ 即可。
"""
import os
import sys
import zipfile
import random
import zlib
import datetime
from xml.sax.saxutils import escape

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACCOUNT = "示例账户-直播"
OUT_DIR = os.path.join(BASE, ACCOUNT)
START = datetime.date(2026, 6, 1)
WEEKS = 10          # 生成 10 周示例数据
DAYS_PER_WEEK = 2   # 每周 2 天（周一/周四）

HEADERS = ["素材名称", "素材ID", "素材评估", "素材时长", "素材创建时间", "素材来源", "标签",
           "整体消耗", "净成交ROI", "净成交金额", "1小时内退款率", "整体支付ROI",
           "整体成交金额", "净成交金额结算率", "净成交订单数"]

# 素材定义：(名称, 创建时间, 峰值日消耗, 活跃天数, 峰值偏移天数, 评估, 来源, 标签, 时长, 停投期天数)
# 停投期天数：活跃期结束后仍出现在报表中的天数（消耗为 0），用于演示"停投"阶段标签。
MATERIALS = [
    ("品牌A-直播-示例产品-1001-20260601-作者甲-新品实拍讲解.mp4", "2026-06-01 10:12:33", 900, 75, 18, "优质", "本地上传", "直播引流", "00:52", 0),
    ("品牌A-直播-示例产品-1002-20260606-作者乙-真实使用效果.mp4", "2026-06-06 14:05:11", 1500, 65, 12, "优质", "本地上传", "直播引流", "01:08", 0),
    ("品牌A-直播-示例产品-1003-20260612-作者甲-开箱全流程.mp4", "2026-06-12 09:40:27", 700, 55, 10, "一般", "本地上传", "直播引流", "01:23", 0),
    ("品牌A-直播-示例产品-1004-20260620-作者丙-限时活动讲解.mp4", "2026-06-20 20:18:05", 1100, 50, 8, "优质", "本地上传", "活动促销", "00:47", 0),
    ("品牌A-种草-示例产品-2001-20260625-作者乙-好物种草口播.mp4", "2026-06-25 11:30:42", 500, 45, 7, "一般", "本地上传", "好物种草", "00:39", 0),
    ("品牌A-种草-示例产品-2002-20260702-作者甲-日常使用场景.mp4", "2026-07-02 16:22:18", 800, 40, 6, "优质", "本地上传", "好物种草", "00:55", 0),
    ("品牌A-混剪-示例产品-3001-20260708-作者丙-多场景混剪.mp4", "2026-07-08 10:05:00", 600, 35, 5, "一般", "本地上传", "混剪", "01:32", 0),
    ("品牌A-混剪-示例产品-3002-20260715-作者乙-达人素材混剪.mp4", "2026-07-15 13:44:56", 450, 30, 4, "一般", "本地上传", "混剪", "01:41", 0),
    ("素材采买-示例产品-作者丁-1-20260720.mp4", "2026-07-20 09:15:30", 350, 25, 4, "优质", "素材采买", "素材采买", "00:33", 0),
    ("品牌A-直播-示例产品-2kg-1005-20260722-作者甲-大规格包装讲解.mp4", "2026-07-22 15:37:09", 950, 20, 3, "同质化", "本地上传", "直播引流", "01:12", 0),
    ("jimeng-2026-07-24-4001-AI生成创意场景.mp4", "2026-07-24 08:52:44", 300, 16, 3, "同质化", "AI生成", "即梦AI", "00:28", 0),
    ("品牌A-直播-示例产品-1006-20260601-作者戊-早期测试素材.mp4", "2026-06-01 10:00:00", 500, 14, 4, "一般", "本地上传", "直播引流", "00:31", 28),
    # 窗口末上新：仅覆盖最后一周 -> 阶段"新素材"
    ("品牌A-直播-示例产品-1007-20260803-作者丙-新品预告讲解.mp4", "2026-08-03 09:20:15", 420, 4, 2, "优质", "本地上传", "直播引流", "00:36", 0),
    # 窗口末仍处上升段：末周消耗递增 -> 阶段"放量中"
    ("品牌A-直播-示例产品-1008-20260720-作者乙-夏季活动预热.mp4", "2026-07-20 11:08:37", 1250, 30, 24, "优质", "本地上传", "活动促销", "01:05", 0),
    # 方括号 AI 标识素材：文案含【AI】-> 演示 name_parser 的 _ai_info 方括号识别
    ("品牌A-直播-示例产品-1009-20260728-作者甲-【AI】智能混剪讲解.mp4", "2026-07-28 10:05:00", 520, 14, 3, "优质", "本地上传", "AI生成", "00:41", 0),
]

AGG_NAME = "AIGC动态创意视频素材集合"


def daily_spend(day_offset, active_days, peak_offset, peak_spend):
    """三角生命周期曲线：上升期→峰值→衰减；范围外返回 0。"""
    if day_offset < 0 or day_offset >= active_days:
        return 0.0
    if day_offset <= peak_offset:
        ratio = 0.25 + 0.75 * (day_offset / peak_offset if peak_offset else 1)
    else:
        ratio = 1.0 - 0.75 * (day_offset - peak_offset) / max(1, active_days - peak_offset)
    return max(0.0, peak_spend * ratio)


def rng_for(mid, day):
    """每个素材每天独立的稳定随机源（可复现）。"""
    return random.Random(zlib.crc32(f"{mid}|{day}".encode("utf-8")))


def build_metrics(spend, rng):
    if spend <= 0:
        return {"spend": 0.0, "net_roi": None, "net_pay": 0.0, "refund": "0.00%",
                "roi": None, "pay": 0.0, "settle": "0.00%", "order": 0}
    roi = round(1.15 + rng.random() * 0.85, 2)
    pay = round(spend * roi, 2)
    settle = 0.86 + rng.random() * 0.13
    net_pay = round(pay * settle, 2)
    order = max(1, round(net_pay / 68))
    refund = round(rng.random() * 0.07, 4)
    net_roi = round(net_pay / spend, 2)
    return {
        "spend": round(spend, 2), "net_roi": net_roi, "net_pay": net_pay,
        "refund": f"{refund * 100:.2f}%", "roi": roi, "pay": pay,
        "settle": f"{settle * 100:.2f}%", "order": order,
    }


def cell_xml(col, text):
    """inlineStr 单元格。"""
    return (f'<c r="{col}" t="inlineStr"><is><t>{escape(str(text))}</t></is></c>')


def row_xml(rn, values):
    cells = []
    for idx, v in enumerate(values):
        col = chr(ord("A") + idx)
        cells.append(cell_xml(col, v))
    return "<row r=\"%d\">%s</row>" % (rn, "".join(cells))


def build_sheet_xml(days_rows):
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>',
        row_xml(1, HEADERS),
    ]
    for rn, values in enumerate(days_rows, start=2):
        parts.append(row_xml(rn, values))
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


CONTENT_TYPES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                 '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                 '<Default Extension="xml" ContentType="application/xml"/>'
                 '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                 '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                 '</Types>')

ROOT_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
             '</Relationships>')

WORKBOOK = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>')

WORKBOOK_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                 '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
                 '</Relationships>')


def write_xlsx(path, days_rows):
    xml = build_sheet_xml(days_rows)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("xl/workbook.xml", WORKBOOK)
        z.writestr("xl/_rels/workbook.xml.rels", WORKBOOK_RELS)
        z.writestr("xl/worksheets/sheet1.xml", xml)


def generate():
    # 生成日期列表：每周取周一、周四
    monday = START - datetime.timedelta(days=START.weekday())
    days = []
    for w in range(WEEKS):
        mon = monday + datetime.timedelta(weeks=w)
        thu = mon + datetime.timedelta(days=3)
        days.append(mon)
        days.append(thu)

    os.makedirs(OUT_DIR, exist_ok=True)
    n_files = 0
    n_rows = 0
    for i, day in enumerate(days):
        day_str = day.isoformat()
        rows = []
        day_total_spend = 0.0
        for idx, (name, created, peak_spend, active_days, peak_off, eva, src, tag, dur, stale) in enumerate(MATERIALS):
            offset = (day - datetime.date.fromisoformat(created[:10])).days
            if offset < 0:
                continue
            if offset >= active_days:
                # 停投期：仍在报表出现但消耗为 0（演示"停投"阶段标签）
                if stale and offset < active_days + stale:
                    spend = 0.0
                else:
                    continue
            else:
                spend = daily_spend(offset, active_days, peak_off, peak_spend)
                if spend <= 0:
                    continue
            mid = f"888800000{idx + 1:05d}"   # 虚构素材 ID：跨天固定，保证唯一键稳定（避开真实 76xx 前缀）
            rng = rng_for(mid, day_str)
            m = build_metrics(spend, rng)
            rows.append([
                name, mid, eva, dur, created, src, tag,
                m["spend"], m["net_roi"], m["net_pay"], m["refund"],
                m["roi"], m["pay"], m["settle"], m["order"],
            ])
            day_total_spend += m["spend"]

        # 聚合行（无 ID）
        agg_spend = round(day_total_spend * 0.18, 2)
        if agg_spend > 0:
            agg_pay = round(agg_spend * 1.10, 2)
            agg_net = round(agg_pay * 0.95, 2)
            agg_order = max(1, round(agg_net / 68))
            rows.append([
                AGG_NAME, "", "优质", "", "", "本地上传", "AIGC",
                agg_spend, round(agg_net / agg_spend, 2), agg_net, "2.00%",
                1.10, agg_pay, "95.00%", agg_order,
            ])

        fname = f"全域数据_素材分析_视频_{day_str} 00_00_00-{day_str} 23_59_59-demo{i + 1:04d}.xlsx"
        write_xlsx(os.path.join(OUT_DIR, fname), rows)
        n_files += 1
        n_rows += len(rows)

    print(f"已生成 {n_files} 个示例日报文件（{START} ~ {days[-1]}，共 {n_rows} 行数据）")
    print(f"目录: {OUT_DIR}")
    print("下一步：python monitor/import_daily.py --account %s" % ACCOUNT)


if __name__ == "__main__":
    generate()
