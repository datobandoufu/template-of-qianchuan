# -*- coding: utf-8 -*-
"""验证自包含看板：页面内嵌 JSON 可解析、无 </script> 截断隐患、关键内容齐全。"""
import os
import re
import json

BASE = os.path.dirname(os.path.abspath(__file__))
idx = os.path.join(BASE, "output", "dashboard", "index.html")
html = open(idx, encoding="utf-8").read()

print("index.html 大小:", len(html), "bytes")

# 1) 提取内嵌 JSON（多账户架构：数据后紧跟 ACCT_EMBEDDED 账户列表）
m = re.search(r"window\.DASH_DATA = (\{.*?\});\nconst ACCT_EMBEDDED", html, re.S)
assert m, "未找到内嵌数据"
# 顺带确认账户切换元素存在
assert "accountSel" in html, "账户切换下拉框缺失！"
print("账户切换下拉框: OK")
raw = m.group(1)
print("内嵌 JSON 长度:", len(raw))

# 2) 检查数据区不包含裸 </script>
assert "</script" not in raw, "数据内包含未转义的 </script>！"
print("无 </script> 截断隐患: OK")

# 3) JSON 可解析
data = json.loads(raw)
print("JSON 有效: 素材数", len(data["materials"]), "| 周数", len(data["weeks"]),
      "| 总量 消耗", data["totals"]["spend"], "实付", data["totals"]["pay"])

# 4) 关键内容存在性
checks = {
    "页面标题": "千川素材监控看板" in html,
    "总览页": "tab-overview" in html,
    "素材页": "tab-materials" in html,
    "新增页": "tab-new" in html,
    "修订页": "tab-revision" in html,
    "ECharts 引入": "echarts" in html,
    "数据含素材卡": '"materials"' in raw,
    "账户列表注入": "ACCOUNTS" in html,
}
for k, v in checks.items():
    print(f"  {k}: {'OK' if v else 'MISSING!'}")

# 5) 顺带确认 data.js 也可解析（供外部使用）
djs = os.path.join(BASE, "output", "dashboard", "data.js")
t = open(djs, encoding="utf-8").read()
d2 = json.loads(t[len("window.DASH_DATA = "):-1])
assert len(d2["materials"]) == len(data["materials"])
print("data.js 并存且一致: OK")
print("ALL CHECKS PASSED" if all(checks.values()) else "SOME CHECKS FAILED")
