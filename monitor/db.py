# -*- coding: utf-8 -*-
"""SQLite 数据层：建库、连接、表结构。

多账户架构（2026-08-20 起）：
- 每个账户（项目根目录下的数据文件夹）拥有独立的数据库文件 data/<账户>.db；
- 默认账户 DEFAULT_ACCOUNT 兼容旧单库：首次运行时自动把根目录旧 materials.db
  迁移复制为 data/<默认账户>.db（原文件保留，仅作备份）；
- get_conn() 不传账户时连接默认账户，传账户时连接对应账户库。
- 使用前请将 DEFAULT_ACCOUNT 改为实际账户名（示例数据默认「示例账户-直播」）。

口径说明（2026-08 起数据源由周报改为日报）：
- daily_stats 按「素材 + 天」存事实，报表层再聚合成 ISO 自然周（周一~周日）。
- 指标字段为 15 列新格式：整体消耗 / 净成交ROI / 净成交金额 / 1小时内退款率 /
  整体支付ROI / 整体成交金额 / 净成交金额结算率 / 净成交订单数。
"""
import os
import shutil
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_ACCOUNT = "示例账户-直播"   # TODO: 按实际账户名修改
DATA_DIR = os.path.join(BASE, "data")
LEGACY_DB = os.path.join(BASE, "materials.db")
DB_PATH = os.path.join(DATA_DIR, DEFAULT_ACCOUNT + ".db")  # 兼容引用，指向默认账户库

SCHEMA = """
CREATE TABLE IF NOT EXISTS import_log (
    file_name    TEXT PRIMARY KEY,
    file_mtime   TEXT,
    file_size    INTEGER,
    period_start TEXT,
    period_end   TEXT,
    row_count    INTEGER,
    imported_at  TEXT
);
CREATE TABLE IF NOT EXISTS materials (
    material_key      TEXT PRIMARY KEY,
    material_id       TEXT,
    name              TEXT,
    duration          TEXT,
    source            TEXT,
    tags              TEXT,
    created_at        TEXT,
    first_seen_day    TEXT,
    latest_evaluation TEXT,
    is_aggregate      INTEGER DEFAULT 0,
    -- 名称拆解派生字段（源数据不动，仅此处新增；由 name_parser 填充）
    channel           TEXT,   -- 渠道（直播/种草/混剪/素材采买/即梦AI…）
    product           TEXT,   -- 归属产品（归一化，精细化不合并品类）
    product_raw       TEXT,   -- 原始产品段
    material_no       TEXT,   -- 素材编号
    created_date      TEXT,   -- 名称中拆出的创作日期 YYYY-MM-DD
    author            TEXT,   -- 内部作者
    mix_author        TEXT,   -- 混剪达人（多个用 / 分隔）
    parse_status      TEXT DEFAULT 'ok',  -- ok / no_author / no_meta / ai / aggregate / nomatch
    -- AI 素材标识（2026-08-21 新增；识别规则见 name_parser._ai_info）
    is_ai             INTEGER DEFAULT 0,  -- 是否 AI 素材（0/1）
    ai_tag            TEXT                -- AI 标识原文（如 AI / AI+机制 / 平台AI裂变）
);
CREATE TABLE IF NOT EXISTS daily_stats (
    material_key   TEXT NOT NULL,
    period_start   TEXT NOT NULL,
    period_end     TEXT NOT NULL,
    evaluation     TEXT,
    spend_total    REAL,   -- 整体消耗
    net_roi        REAL,   -- 净成交ROI（净成交金额÷整体消耗）
    net_pay        REAL,   -- 净成交金额
    refund_rate_1h REAL,   -- 1小时内退款率（0~1）
    roi            REAL,   -- 整体支付ROI（整体成交金额÷整体消耗）
    pay_total      REAL,   -- 整体成交金额
    settle_rate    REAL,   -- 净成交金额结算率（0~1）
    order_count    REAL,   -- 净成交订单数
    source         TEXT,
    updated_at     TEXT,
    PRIMARY KEY (material_key, period_start)
);
CREATE TABLE IF NOT EXISTS revision_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    material_key TEXT,
    period_start TEXT,
    field        TEXT,
    old_value    TEXT,
    new_value    TEXT,
    revised_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_daily_period  ON daily_stats(period_start);
CREATE INDEX IF NOT EXISTS idx_materials_first ON materials(first_seen_day);
"""


def ensure_db_dir():
    """创建 data/ 目录；若默认账户库尚不存在而根目录存在旧单库，则迁移一份。

    用 SQLite 的 backup API 复制，保证 WAL 中尚未 checkpoint 的数据也完整迁移；
    原 materials.db 保留，仅作备份。
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    target = os.path.join(DATA_DIR, DEFAULT_ACCOUNT + ".db")
    if not os.path.exists(target) and os.path.exists(LEGACY_DB):
        try:
            src = sqlite3.connect(LEGACY_DB)
            try:
                dst = sqlite3.connect(target)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
            finally:
                src.close()
            print(f"已迁移旧数据库: {LEGACY_DB} -> {target}（原文件保留）")
        except sqlite3.Error as e:
            print(f"警告：迁移旧数据库失败: {e}")


def db_path_for(account=None):
    """账户名 -> 数据库文件路径。"""
    return os.path.join(DATA_DIR, (account or DEFAULT_ACCOUNT) + ".db")


def get_conn(account=None):
    """返回带 dict 行工厂的连接（指定账户库；缺省为默认账户）。"""
    ensure_db_dir()
    conn = sqlite3.connect(db_path_for(account))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def migrate(account=None):
    """为已有库补充新列（CREATE TABLE IF NOT EXISTS 不会给旧表加列）。"""
    conn = get_conn(account)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(materials)")}
    adds = {
        "channel": "TEXT", "product": "TEXT", "product_raw": "TEXT",
        "material_no": "TEXT", "created_date": "TEXT",
        "author": "TEXT", "mix_author": "TEXT",
        "parse_status": "TEXT DEFAULT 'ok'",
        "is_ai": "INTEGER DEFAULT 0", "ai_tag": "TEXT",
    }
    for c, t in adds.items():
        if c not in cols:
            conn.execute(f"ALTER TABLE materials ADD COLUMN {c} {t}")
    conn.commit()
    conn.close()


def init_db(account=None):
    ensure_db_dir()
    conn = get_conn(account)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    migrate(account)


if __name__ == "__main__":
    init_db()
    print("DB ready:", DB_PATH)
