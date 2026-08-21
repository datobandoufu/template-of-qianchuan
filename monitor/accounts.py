# -*- coding: utf-8 -*-
"""账户（数据源）发现与元信息。

多账户架构（2026-08-20 起）：
- 账户 = 项目根目录下的一个数据文件夹（如「示例账户-直播」「示例账户-旗舰店」），
  文件夹内存放每日导出的天级 xlsx；
- 每个账户拥有独立的数据库 data/<账户>.db，看板/周报按账户分别生成；
- 账户文件夹暂时为空（尚未导入数据）也允许出现在列表中，便于后续补数据。

说明：
- 扫描根目录时排除系统目录（monitor / output / data 等）与隐藏目录（.git 等）；
- 新增数据源时只需新建文件夹并把 xlsx 放进去，即可被自动识别为账户。
"""
import os
import sqlite3

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE, "data")

# 项目系统目录：不作为账户参与扫描
SYSTEM_DIRS = {
    "monitor", "output", "data", "backup", "docs", "scripts",
    "dist", "build", "通用模板",
    "__pycache__", "node_modules", ".git", ".svn", ".hg",
    ".workbuddy", ".codebuddy", ".idea", ".vscode",
}


def discover_accounts():
    """扫描项目根目录，返回全部账户（文件夹名）列表，按名称排序。"""
    out = []
    try:
        names = sorted(os.listdir(BASE))
    except OSError:
        return out
    for name in names:
        if name.startswith("."):
            continue
        if name in SYSTEM_DIRS:
            continue
        if os.path.isdir(os.path.join(BASE, name)):
            out.append(name)
    return out


def account_db_path(account):
    """返回账户对应的数据库文件路径（data/<账户>.db）。"""
    return os.path.join(DATA_DIR, account + ".db")


def account_has_data(account):
    """账户是否已入库数据（对应库文件存在且 daily_stats 表非空）。"""
    path = account_db_path(account)
    if not os.path.exists(path):
        return False
    try:
        conn = sqlite3.connect(path)
        try:
            n = conn.execute("SELECT COUNT(*) FROM daily_stats").fetchone()[0]
        finally:
            conn.close()
        return n > 0
    except sqlite3.Error:
        return False


if __name__ == "__main__":
    accts = discover_accounts()
    print("发现账户: %d 个" % len(accts))
    for a in accts:
        print("  %-24s 有数据=%s" % (a, account_has_data(a)))
