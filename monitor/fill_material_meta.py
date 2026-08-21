# -*- coding: utf-8 -*-
"""回填素材归属字段：读取 materials 全部名称 -> name_parser 拆解 -> 写入新派生字段。

多账户架构：默认遍历全部有数据的账户，也可用 --account 指定单个。
一次性脚本，用于已有数据库补填；日常增量导入由 import_daily.py 自动拆解。
源 xlsx 与 daily_stats 原始数据不动。
"""
import os
import sys
import argparse
import collections

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from db import get_conn, init_db, db_path_for
from accounts import discover_accounts
from name_parser import parse, build_author_names

FIELDS = ["channel", "product", "product_raw", "material_no",
          "created_date", "author", "mix_author", "parse_status",
          "is_ai", "ai_tag"]


def fill_account(account):
    if not os.path.exists(db_path_for(account)):
        return 0
    init_db(account)
    conn = get_conn(account)
    rows = conn.execute(
        "SELECT material_key, name FROM materials WHERE name IS NOT NULL AND name != ''").fetchall()
    if not rows:
        conn.close()
        return 0
    authors = build_author_names(conn)
    print(f"[{account}] 作者名单: {sorted(authors)}")
    print(f"[{account}] 待回填素材: {len(rows)}")

    stats = collections.Counter()
    ai_cnt = 0
    n = 0
    for r in rows:
        meta = parse(r["name"], authors)
        conn.execute(
            "UPDATE materials SET channel=?, product=?, product_raw=?, material_no=?,"
            " created_date=?, author=?, mix_author=?, parse_status=?, is_ai=?, ai_tag=?"
            " WHERE material_key=?",
            (meta["channel"], meta["product"], meta["product_raw"], meta["material_no"],
             meta["created_date"], meta["author"], meta["mix_author"],
             meta["parse_status"], meta["is_ai"], meta["ai_tag"], r["material_key"]))
        stats[meta["parse_status"]] += 1
        if meta["is_ai"]:
            ai_cnt += 1
        n += 1
        if n % 500 == 0:
            conn.commit()
    conn.commit()
    conn.close()

    total = len(rows)
    print(f"[{account}] AI 素材识别: {ai_cnt} 个")
    print(f"[{account}] === 拆解质量统计 ===")
    for k, v in stats.most_common():
        print(f"[{account}]   {k}: {v} ({v/total*100:.1f}%)")

    conn = get_conn(account)
    print(f"[{account}] === AI 标识分布 ===")
    for r in conn.execute("SELECT ai_tag, COUNT(*) c FROM materials WHERE is_ai=1"
                          " GROUP BY ai_tag ORDER BY c DESC"):
        print(f"[{account}]   {r['ai_tag']}: {r['c']}")
    conn.close()
    return n


def main():
    parser = argparse.ArgumentParser(description="回填素材归属字段（含 AI 标识识别）")
    parser.add_argument("--account", help="仅回填该账户（缺省遍历全部有数据账户）")
    args = parser.parse_args()

    accounts = [args.account] if args.account else discover_accounts()
    if not accounts:
        print("未发现任何账户文件夹。")
        return
    print("待回填账户: " + "、".join(accounts))
    for account in accounts:
        n = fill_account(account)
        if n == 0:
            print(f"[{account}] 无数据或库不存在，跳过。")
    print("回填完成。")


if __name__ == "__main__":
    main()
