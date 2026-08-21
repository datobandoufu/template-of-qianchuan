# 千川素材监控体系 · 通用模板

> 本目录是一份**可复用的通用模板**，不含任何业务数据与机密信息。
> 复制本模板到新的项目目录后，按下方「接入步骤」配置即可独立运行。

对千川「全域数据-素材分析-视频」**日报** xlsx 的自动监控：
入库（天级事实）→ 聚合成 ISO 自然周 → 素材生命周期跟踪 → 每周新增素材分析 → Excel 周报 + 本地网页看板。

支持 **AI 素材识别**：按素材名称自动识别方括号【AI】标识与平台 AI 裂变命名，
看板与周报内置 AI 素材专项页（每周新增 / 排行 / ROI 分布 / 作者汇总 / 标识汇总）。

支持**多账户（多数据源）**：项目根目录下每个数据文件夹即一个账户，各账户数据独立存储、
独立生成周报与看板，看板顶部可一键切换账户，图表与数据逻辑完全复用。

## 目录结构

```
<项目根目录>\
├── <账户1>文件夹\              ① 监控源：每个数据文件夹=一个账户，每日导出的 xlsx 放入其中
│    └── …                      （文件名含单日周期，如 ...2026-08-16 00_00_00-...xlsx）
├── data\                       ② 数据库：每账户独立 data/<账户>.db（自动创建）
├── monitor\                    ③ 程序代码
│   ├── accounts.py             账户（数据源）发现与元信息
│   ├── db.py                   SQLite 数据层（4 张表，按账户分库）
│   ├── parse_xlsx.py           inlineStr 型 xlsx 解析（15 列新格式）
│   ├── name_parser.py          素材名称拆解（产品/渠道/作者/混剪达人/编号/创作日期/AI标识）
│   ├── fill_material_meta.py   一次性回填素材归属字段
│   ├── import_daily.py         一键导入入口（自动扫描全部账户，天级入库）
│   ├── metrics.py              派生指标引擎（天→周聚合）
│   ├── report_excel.py         Excel 周报生成（按账户分别输出）
│   ├── report_dashboard.py     网页看板生成（每账户一个数据文件 + 前端切换）
│   ├── dashboard_app.py        桌面应用入口（系统托盘，无 cmd 窗口）
│   └── templates\index.html    看板页面模板（含账户切换下拉框）
├── output\                     ④ 生成物（周报 xlsx、dashboard\index.html 看板）
├── 一键导入.bat                双击：扫描全部账户，导入新文件 + 刷新全部报表
├── 启动看板.bat                兼容入口：优先启动桌面应用 exe，找不到时回退 Python 方式
└── verify_dashboard.py / verify_outputs.py   校验脚本
```

## 接入步骤（新项目初始化）

1. **复制模板**：将本目录内容复制为新项目根目录（`monitor\`、`一键导入.bat`、`.gitignore` 等同级）；
2. **设置默认账户**：修改 `monitor/db.py` 中的 `DEFAULT_ACCOUNT` 为你的默认账户名；
3. **建立账户文件夹**：在项目根目录新建数据文件夹（如 `示例账户-直播\`），把官方日报 xlsx 放进去；
4. **导入数据**：双击 `一键导入.bat`（或 `python monitor\import_daily.py`）；
5. **查看看板**：双击 `启动看板.bat`（或先打包桌面应用），浏览器访问 http://127.0.0.1:8931。

## 配置项（按需调整）

| 位置 | 配置 | 说明 |
|---|---|---|
| `monitor/db.py` | `DEFAULT_ACCOUNT` | 默认账户名（必改） |
| `monitor/name_parser.py` | `PRODUCT_NORMALIZE` | 产品规格归并映射（如 `示例产品-2kg → 示例产品`） |
| `monitor/name_parser.py` | `KNOWN_AUTHORS` | 默认内部作者名单（留空则由数据学习扩充） |
| `monitor/templates/index.html` | `FULLTIME_AUTHORS` | 「全职作者」名单，用于全职/其他分组 |
| `monitor/templates/index.html` | `lineOf()` / `LINE_COLORS` | 产品线兜底关键词与配色 |
| `启动看板.bat` / `一键导入.bat` | `PY` | 默认使用系统 PATH 中的 python |

> 素材名称拆解规则基于「`品牌-渠道-产品-编号-日期-作者-文案`」约定，
> 若你的命名规范不同，请同步调整 `monitor/name_parser.py` 中的正则。

## 示例数据（预览项目效果）

模板已附带**虚构示例数据**（`示例账户-直播\`，20 个天级日报，2026-06-01 ~ 2026-08-06），
不含任何真实业务信息，用于快速预览看板与周报效果。

```bat
:: 一键导入示例数据并生成周报/看板
一键导入.bat
:: 或
python monitor\import_daily.py

:: 查看 output\dashboard\index.html 或双击 启动看板.bat
```

示例数据覆盖：直播/种草/混剪/素材采买/即梦AI 渠道，新素材/放量中/稳定/衰退/停投 全阶段标签，
同质化预警、聚合行、产品规格归并、AI 素材识别（即梦AI /【AI】标识）等场景。

- **重新生成示例数据**：`python monitor\generate_sample_data.py`
- **重置为空白模板**：删除 `示例账户-直播\` 文件夹及 `data\`、`output\` 即可；
  如需空白看板模板，同时将 `monitor\templates\index.html` 中的示例作者
  `FULLTIME_AUTHORS = ['作者甲','作者乙']` 改回 `[]`。

## 使用流程（每天一次）

1. 从千川后台导出当天「全域数据-素材分析-视频」xlsx，文件名保持官方默认格式
   （含单日周期，如 `...2026-08-16 00_00_00-2026-08-16 23_59_59-xxx.xlsx`），放入对应账户文件夹；
2. 双击 **一键导入.bat**：自动识别全部账户的新文件 → 天级入库 → 刷新各账户 Excel 周报与网页看板；
3. 查看：Excel 周报在 `output\`；看板在 `output\dashboard\index.html`（或双击 `启动看板.bat`）。

> 重复导入同一文件是安全的（幂等）：不会产生重复数据；官方回调修正历史天数据时，
> 重新导入会覆盖为新值并记录修订痕迹，可在「修订记录」Sheet/页面追溯。

## 多账户说明

- **账户 = 根目录数据文件夹**：新增数据源时新建文件夹放 xlsx 即可被自动识别
  （自动排除 `monitor/output/data/dist/build` 等系统目录）；
- **数据隔离**：每账户独立数据库 `data/<账户>.db`，互不影响；
  单独导入：`python monitor\import_daily.py --account 账户名`；
- **看板切换**：顶部「账户/数据源」下拉框一键切换（`?account=账户`），
  无数据账户不会出现在下拉框中。

## 桌面应用（可选）

```bat
:: 安装打包依赖（首次）
pip install pyinstaller pystray pillow

:: 打包为无窗口单文件 exe（生成在 dist\，复制到项目根目录）
python -m PyInstaller --onefile --noconsole --name "千川素材监控看板" --collect-all pystray --collect-all PIL monitor\dashboard_app.py
```

- exe 启动后系统托盘运行，无 cmd 窗口；服务绑定 `0.0.0.0`，可经内网穿透对外提供访问；
- 单实例保护：已运行时重复双击仅打开看板；托盘菜单可「打开看板 / 重启服务 / 退出」；
- 运行日志写入 `看板服务.log`；
- **端口与冲突防护**：默认 `8931`；若同一台机器上已运行其他项目的看板（端口被占用），
  启动脚本会明确提示而非误连他人服务。与其他项目共存时请将 `monitor/dashboard_app.py` 的
  `PORT` 与 `启动看板.bat` 的 `PORT` 改成不同端口（如 8932）；
- **数据存在性检查**：若本项目尚未生成 `output/dashboard/index.html`，启动脚本会提示
  「先运行一键导入」，不会启动空服务或误显示其他项目的数据。

## 数据口径（15 列新格式）

| 项 | 口径 |
|---|---|
| 粒度 | 数据库按「素材 + 天」存事实（daily_stats）；报表统一聚合成 **ISO 自然周（周一~周日）** |
| 整体ROI | 整体成交金额 ÷ 整体消耗 |
| 净成交ROI | 净成交金额 ÷ 整体消耗 |
| 退款率/结算率 | 周聚合时按对应成交金额加权 |
| 每周新增（口径A/B） | 按素材创建时间 / 按首次出现在周报中 |
| 次周留存 | 新增素材次周是否继续投放 |
| 阶段标签 | 🆕新素材 · 📈放量中 · 📉衰退 · ⏸️停投 · 稳定 |
| 素材唯一键 | 素材ID；缺失时按名称哈希兜底 |
| AI 素材识别 | 名称含方括号 `【AI】` 标识 → 取标识原文；行首/连字符/下划线后的 `AI` 段 → `平台AI裂变`；聚合行（如 `AIGC…集合`）不视为单素材 AI |
| 聚合行 | 无 ID 的集合/汇总行标记为「聚合」，不参与单素材去重 |

源表字段（15 列）：
`素材名称 / 素材ID / 素材评估 / 素材时长 / 素材创建时间 / 素材来源 / 标签 / 整体消耗 / 净成交ROI / 净成交金额 / 1小时内退款率 / 整体支付ROI / 整体成交金额 / 净成交金额结算率 / 净成交订单数`

## 常用命令

```bat
:: 重新生成报表（不重新导入）
python monitor\report_excel.py
python monitor\report_dashboard.py

:: 单独导入某账户
python monitor\import_daily.py --account 示例账户-直播

:: 全量重建某账户数据库（慎用，清空后重新导入该账户全部文件）
del data\示例账户-直播.db
python monitor\import_daily.py --account 示例账户-直播

:: 校验
python verify_dashboard.py
python verify_outputs.py
```
