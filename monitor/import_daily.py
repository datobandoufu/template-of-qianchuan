# -*- coding: utf-8 -*-
"""一键导入入口（天级数据源）。

多账户架构（2026-08-20 起）：
- 账户 = 项目根目录下的数据文件夹，每账户对应 data/<账户>.db；
- 默认自动扫描全部账户，逐个导入新文件/变更文件（支持 --account 指定单个）；
- 每账户流程相同：扫描账户文件夹 -> 仅导入新文件/变更文件 ->
  入库(素材主档 + 天级事实 daily_stats，同天覆盖并记录修订痕迹)。
之后统一刷新所有账户的 Excel 周报(天聚合成 ISO 自然周) + 网页看板。

幂等：重复运行不会产生重复数据；同一 (素材, 天) 只保留一份。
文件名为单日周期，如 ...2026-08-16 00_00_00-2026-08-16 23_59_59-xxx.xlsx。
"""
import os
import re
import sys
import glob
import argparse
import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_conn, init_db
from accounts import discover_accounts
from parse_xlsx import parse_rows, normalize_row, material_key, is_aggregate_row
from name_parser import parse as parse_name, build_author_names

PERIOD_RE = re.compile(r"(\d{4}-\d{2}-\d{2}) 00_00_00-(\d{4}-\d{2}-\d{2})")

# daily_stats 中参与修订对比的字段（数值/文本）
STAT_FIELDS = ["spend_total", "net_roi", "net_pay", "refund_rate_1h",
               "roi", "pay_total", "settle_rate", "order_count",
               "evaluation", "source"]


def now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def source_dir(account):
    """账户 -> 数据文件夹路径。"""
    return os.path.join(BASE, account)


# 惰性加载的作者名单（按账户缓存，供缺作者场景判定）
_author_names = {}


def _get_author_names(conn, account):
    if account not in _author_names:
        _author_names[account] = build_author_names(conn)
    return _author_names[account]


def discover_files(account):
    """返回指定账户待导入文件列表：(路径, 文件名, mtime, size)。"""
    conn = get_conn(account)
    candidates = []
    for f in sorted(glob.glob(os.path.join(source_dir(account), "*.xlsx"))):
        name = os.path.basename(f)
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%Y-%m-%d %H:%M:%S")
        size = os.path.getsize(f)
        row = conn.execute(
            "SELECT file_mtime, file_size FROM import_log WHERE file_name=?", (name,)).fetchone()
        if row is None or row["file_mtime"] != mtime or row["file_size"] != size:
            candidates.append((f, name, mtime, size))
    conn.close()
    return candidates


def import_file(conn, account, f, name, mtime, size):
    """导入单个文件，返回导入行数。"""
    header, raw_rows = parse_rows(f)
    m = PERIOD_RE.search(name)
    if not m:
        print(f"  ! 无法从文件名识别周期，跳过: {name}")
        return 0
    period_start, period_end = m.group(1), m.group(2)
    n = 0
    for cells in raw_rows:
        row = normalize_row(cells)
        if not row["name"] and not row["mid"]:
            continue
        key = material_key(row)
        agg = 1 if is_aggregate_row(row) else 0
        meta = parse_name(row["name"], _get_author_names(conn, account))

        # 素材主档 upsert（first_seen_day 只写首次；文件按日期升序扫描，首见即最早一天）
        exists = conn.execute(
            "SELECT first_seen_day FROM materials WHERE material_key=?", (key,)).fetchone()
        if exists is None:
            conn.execute(
                "INSERT INTO materials(material_key, material_id, name, duration, source, tags,"
                " created_at, first_seen_day, latest_evaluation, is_aggregate,"
                " channel, product, product_raw, material_no, created_date, author,"
                " mix_author, parse_status, is_ai, ai_tag)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (key, row["mid"], row["name"], row["duration"], row["source"], row["tags"],
                 row["created_at"], period_start, row["evaluation"], agg,
                 meta["channel"], meta["product"], meta["product_raw"], meta["material_no"],
                 meta["created_date"], meta["author"], meta["mix_author"], meta["parse_status"],
                 meta["is_ai"], meta["ai_tag"]))
        else:
            conn.execute(
                "UPDATE materials SET material_id=?, name=?, duration=?, source=?, tags=?,"
                " created_at=?, latest_evaluation=?, channel=?, product=?, product_raw=?,"
                " material_no=?, created_date=?, author=?, mix_author=?, parse_status=?,"
                " is_ai=?, ai_tag=? WHERE material_key=?",
                (row["mid"], row["name"], row["duration"], row["source"], row["tags"],
                 row["created_at"], row["evaluation"],
                 meta["channel"], meta["product"], meta["product_raw"], meta["material_no"],
                 meta["created_date"], meta["author"], meta["mix_author"], meta["parse_status"],
                 meta["is_ai"], meta["ai_tag"], key))

        # 天级事实 upsert + 修订痕迹
        prev = conn.execute(
            "SELECT * FROM daily_stats WHERE material_key=? AND period_start=?",
            (key, period_start)).fetchone()
        if prev is not None:
            for fd in STAT_FIELDS:
                ov, nv = prev[fd], row.get(fd)
                if ov != nv:
                    conn.execute(
                        "INSERT INTO revision_log(material_key, period_start, field, old_value,"
                        " new_value, revised_at) VALUES(?,?,?,?,?,?)",
                        (key, period_start, fd, str(ov), str(nv), now_str()))
            conn.execute(
                "UPDATE daily_stats SET evaluation=?, spend_total=?, net_roi=?, net_pay=?,"
                " refund_rate_1h=?, roi=?, pay_total=?, settle_rate=?, order_count=?,"
                " source=?, updated_at=? WHERE material_key=? AND period_start=?",
                (row["evaluation"], row["spend_total"], row["net_roi"], row["net_pay"],
                 row["refund_rate_1h"], row["roi"], row["pay_total"], row["settle_rate"],
                 row["order_count"], row["source"], now_str(), key, period_start))
        else:
            conn.execute(
                "INSERT INTO daily_stats(material_key, period_start, period_end, evaluation,"
                " spend_total, net_roi, net_pay, refund_rate_1h, roi, pay_total, settle_rate,"
                " order_count, source, updated_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (key, period_start, period_end, row["evaluation"], row["spend_total"],
                 row["net_roi"], row["net_pay"], row["refund_rate_1h"], row["roi"],
                 row["pay_total"], row["settle_rate"], row["order_count"],
                 row["source"], now_str()))
        n += 1

    conn.execute(
        "INSERT INTO import_log(file_name, file_mtime, file_size, period_start, period_end,"
        " row_count, imported_at) VALUES(?,?,?,?,?,?,?)"
        " ON CONFLICT(file_name) DO UPDATE SET file_mtime=excluded.file_mtime,"
        " file_size=excluded.file_size, period_start=excluded.period_start,"
        " period_end=excluded.period_end, row_count=excluded.row_count,"
        " imported_at=excluded.imported_at",
        (name, mtime, size, period_start, period_end, n, now_str()))
    conn.commit()
    return n


def import_account(account):
    """导入单个账户的新文件，返回导入文件数。"""
    init_db(account)
    conn = get_conn(account)
    files = discover_files(account)
    if files:
        total = 0
        for f, name, mtime, size in files:
            print(f"[{account}] 导入: {name}")
            n = import_file(conn, account, f, name, mtime, size)
            print(f"  -> {n} 行")
            total += n
        print(f"[{account}] 共导入 {len(files)} 个文件 / {total} 行")
    else:
        print(f"[{account}] 没有新文件需要导入（所有日报均已入库）。")
    conn.close()
    return len(files)


def main():
    parser = argparse.ArgumentParser(description="千川素材监控 - 天级日报导入")
    parser.add_argument("--account", help="仅导入该账户（缺省自动扫描全部账户文件夹）")
    args = parser.parse_args()

    accounts = [args.account] if args.account else discover_accounts()
    if not accounts:
        print("未发现任何账户文件夹（请先在项目根目录新建数据文件夹并放入 xlsx）。")
        return
    print("待处理账户: " + "、".join(accounts))

    n_account = 0
    for account in accounts:
        n_account += import_account(account)
    if n_account == 0:
        print("本次没有新文件需要导入（所有日报均已入库）。")

    print("刷新 Excel 周报（按账户分别生成，天级聚合为 ISO 自然周）...")
    from report_excel import generate_all_excel_reports
    generate_all_excel_reports()

    print("刷新网页看板...")
    from report_dashboard import generate_dashboard
    generate_dashboard()

    print("完成。输出目录: output/")


if __name__ == "__main__":
    main()
