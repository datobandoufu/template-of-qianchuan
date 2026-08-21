# -*- coding: utf-8 -*-
"""素材名称拆解引擎：产品 / 渠道 / 编号 / 创作日期 / 作者 / 混剪达人。

命名结构（约 96% 素材）：{品牌}-{渠道}-{产品}-{编号}-{日期8位}-{作者}-{文案}.mp4
例：品牌A-直播-示例产品-1084-20250423-作者甲-文案描述.mp4

产品归类原则（用户约束）：
- 保持精细化，绝不按品类合并（示例猫砂A/示例猫砂B、示例猫粮A/示例猫粮B 各自独立）。
- 仅对「同一产品的不同规格」做归并（示例产品-2kg/示例产品-8kg → 示例产品），映射表可配置。

拆解结果只写入 materials 表的新增派生字段，源 xlsx 与 daily_stats 原始数据不动。
"""
import re

# ---------------------------------------------------------------
# 产品规格归并（同产品不同规格 → 统一产品名；不要加入品类级合并！）
# ---------------------------------------------------------------
PRODUCT_NORMALIZE = {
    "示例产品-2kg": "示例产品",
    "示例产品-8kg": "示例产品",
}

# 默认内部作者名单（用于"缺作者"场景判定；可在回填时由数据学习扩充）
KNOWN_AUTHORS = set()

# 标准模式：品牌-渠道-产品-编号-日期(8位，容错9位)-作者-文案
_STD8 = re.compile(
    r"^(?P<brand>[^-]+)-(?P<channel>[^-]+)-(?P<product>.+?)"
    r"-(?P<no>\d+)-(?P<date>\d{8,9})-(?P<author>[^-]+)-(?P<copy>.+?)(?:\.mp4)?$")
# 6 位日期变体（如 品牌A-混剪-示例产品-3312-240704-作者甲-...）
_STD6 = re.compile(
    r"^(?P<brand>[^-]+)-(?P<channel>[^-]+)-(?P<product>.+?)"
    r"-(?P<no>\d+)-(?P<date>\d{6})-(?P<author>[^-]+)-(?P<copy>.+?)(?:\.mp4)?$")
# 缺作者兜底：品牌-渠道-产品-编号-日期-尾部（尾部可能是 作者-文案 或 直接文案）
_NOAUTHOR = re.compile(
    r"^(?P<brand>[^-]+)-(?P<channel>[^-]+)-(?P<product>.+?)"
    r"-(?P<no>\d+)-(?P<date>\d{8,9})-(?P<tail>.+?)(?:\.mp4)?$")
# 即梦 AI 生成：jimeng-2026-02-28-编号-文案
_JIMENG = re.compile(
    r"^jimeng-(?P<date>\d{4}-\d{2}-\d{2})-(?P<no>\d+)-(?P<copy>.+?)(?:\.mp4)?$")
# 素材采买：素材采买-产品-作者-1-日期（前缀可能带 一键修复_ 等）
_CAIGOU = re.compile(
    r"^.*素材采买-(?P<product>[^-]+)-(?P<author>[^-]+)-1-(?P<date>\d{8})(?:\.mp4)?$")
# 无日期/无作者结构：品牌-渠道-产品-编号-文案（如 品牌A-种草-示例产品-1325-文案）
_NODATE = re.compile(
    r"^(?P<brand>[^-]+)-(?P<channel>[^-]+)-(?P<product>.+?)"
    r"-(?P<no>\d+)-(?P<copy>.+?)(?:\.mp4)?$")
# 混剪达人标记：【达人混剪-XX-YY】
_MIX = re.compile(r"【达人混剪-([^】]+)】")

# ---------------------------------------------------------------
# AI 素材识别（2026-08-21 新增需求）
#   - 方括号 AI 标识：【AI】【AI+机制】【AI开头+机制+卖点】…（忽略大小写）
#   - 平台 AI 裂变命名：行首/连字符/下划线后的 AI 段（AI示例品牌-…、一键修复_AI-…、素材采买-AI…）
#     用负向断言排除 AIGC（聚合行"…AIGC…集合"由 is_aggregate 标记，不视为单素材 AI）
# ---------------------------------------------------------------
_AI_TAG = re.compile(r"【([^】]*AI[^】]*)】", re.IGNORECASE)
_AI_SEG = re.compile(r"(?:^|[-_])AI(?![A-Z])", re.IGNORECASE)


def _ai_info(name):
    """AI 素材识别：返回 (is_ai, ai_tag)。
    优先级：方括号 AI 标识 > 平台 AI 裂变前缀段。"""
    if not name:
        return 0, None
    m = _AI_TAG.search(name)
    if m:
        return 1, m.group(1).strip()
    if _AI_SEG.search(name):
        return 1, "平台AI裂变"
    return 0, None


def _date_of(s):
    """6/8/9 位数字日期串 → YYYY-MM-DD（9 位取前 8 位容错）；非法返回 None。"""
    if s is None:
        return None
    s = s.strip()
    if len(s) == 9 and s.isdigit():
        s = s[:8]
    if len(s) == 8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) == 6 and s.isdigit():
        return f"20{s[0:2]}-{s[2:4]}-{s[4:6]}"
    return None


def _normalize_product(raw):
    """产品规格归并；无映射则保持原名（精细化，不做品类合并）。"""
    return PRODUCT_NORMALIZE.get(raw, raw)


def _mix_authors(copy):
    """从文案提取混剪达人：多个用 / 分隔；无则 None。"""
    m = _MIX.search(copy or "")
    if not m:
        return None
    parts = [p.strip() for p in m.group(1).split("-") if p.strip()]
    return "/".join(parts) if parts else None


def parse(name, author_names=None):
    """拆解素材名称。返回 dict；author_names 为已知作者名单（缺作者场景判定用）。"""
    known = set(author_names) if author_names else set(KNOWN_AUTHORS)
    name = (name or "").strip()
    r = {
        "channel": None, "product": None, "product_raw": None,
        "material_no": None, "created_date": None,
        "author": None, "mix_author": None, "parse_status": "ok",
        "is_ai": 0, "ai_tag": None,
    }
    if not name:
        r["parse_status"] = "empty"
        return r

    # AI 标识识别（聚合行除外，见下方聚合分支强制清零）
    r["is_ai"], r["ai_tag"] = _ai_info(name)

    # 聚合行（无 ID 的集合/汇总）
    if ("集合" in name or "汇总" in name) and not re.search(r"-\d+-\d{8}-", name):
        r["parse_status"] = "aggregate"
        r["is_ai"], r["ai_tag"] = 0, None
        return r

    m = _STD8.match(name)
    if not m:
        m = _STD6.match(name)
    if m:
        r["channel"] = m.group("channel")
        r["product_raw"] = m.group("product")
        r["product"] = _normalize_product(m.group("product"))
        r["material_no"] = m.group("no")
        r["created_date"] = _date_of(m.group("date"))
        r["author"] = m.group("author")
        r["mix_author"] = _mix_authors(m.group("copy"))
        return r

    # 缺作者兜底（6位日期版本也允许）
    m = _NOAUTHOR.match(name)
    if not m:
        m = re.compile(
            r"^(?P<brand>[^-]+)-(?P<channel>[^-]+)-(?P<product>.+?)"
            r"-(?P<no>\d+)-(?P<date>\d{6})-(?P<tail>.+?)(?:\.mp4)?$").match(name)
    if m:
        tail = m.group("tail")
        r["channel"] = m.group("channel")
        r["product_raw"] = m.group("product")
        r["product"] = _normalize_product(m.group("product"))
        r["material_no"] = m.group("no")
        r["created_date"] = _date_of(m.group("date"))
        # 尾部首段若在作者名单 → 视为作者；否则作者未知
        segs = tail.split("-", 1)
        if segs and segs[0].strip() in known:
            r["author"] = segs[0].strip()
            r["mix_author"] = _mix_authors(segs[1] if len(segs) > 1 else "")
        else:
            r["parse_status"] = "no_author"
            r["mix_author"] = _mix_authors(tail)
        return r

    # 素材采买系列：素材采买-产品-作者-1-日期
    m = _CAIGOU.match(name)
    if m:
        r["channel"] = "素材采买"
        r["product_raw"] = m.group("product")
        r["product"] = _normalize_product(m.group("product"))
        r["author"] = m.group("author")
        r["created_date"] = _date_of(m.group("date"))
        return r

    # 即梦 AI 生成素材（需在"无日期"变体之前，避免误匹配）
    m = _JIMENG.match(name)
    if m:
        r["channel"] = "即梦AI"
        r["created_date"] = m.group("date")
        r["material_no"] = m.group("no")
        r["mix_author"] = _mix_authors(m.group("copy"))
        r["parse_status"] = "ai"
        return r
    if name.startswith("jimeng"):
        r["channel"] = "即梦AI"
        r["parse_status"] = "ai"
        return r

    # 无日期/无作者结构：品牌-渠道-产品-编号-文案
    m = _NODATE.match(name)
    if m:
        r["channel"] = m.group("channel")
        r["product_raw"] = m.group("product")
        r["product"] = _normalize_product(m.group("product"))
        r["material_no"] = m.group("no")
        r["mix_author"] = _mix_authors(m.group("copy"))
        r["parse_status"] = "no_meta"
        return r

    # 纯文案 / 无法识别
    r["parse_status"] = "nomatch"
    return r


def build_author_names(conn):
    """从 materials 已解析素材学习作者名单（标准模式内 author 字段去重）。"""
    rows = conn.execute(
        "SELECT DISTINCT name FROM materials WHERE name IS NOT NULL AND name != ''").fetchall()
    names = set()
    for row in rows:
        m = _STD8.match(row["name"] or "")
        if m and m.group("author"):
            names.add(m.group("author"))
    return names | set(KNOWN_AUTHORS)
