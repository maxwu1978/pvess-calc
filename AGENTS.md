# 11CAD 家庭储能 — Codex 项目约定

## 项目目标

参数驱动的住宅 PV + ESS 方案评估工具。`inputs.yaml` → NEC 计算 → Markdown 报告 + QET 单线图。方案敲定后导出 DXF 给 AutoCAD Electrical 做正式报批。

## 工作流

1. 编辑 `projects/<id>/inputs.yaml`
2. `pvess-calc projects/<id>/` → 生成 `output/calculation.json` 和 `output/report.md`
3. `pvess-render projects/<id>/` → 把计算结果注入 `library/templates/residential-ess-v0.qet`，输出 `output/system.qet`
4. 在 QElectroTech v0.90 里打开 `output/system.qet`（双击 .qet 文件，或先无参启动 QET 再 File → Open；**不要**用 `open -a app file`，会触发 QET 内部导出模式）

## QET 模板

### Phase 0 文本注释模板

模板用 v0.90 schema（`version="0.80"`，rich-HTML 文本注释）。由 `src/pvess_calc/qet/template.py` 生成：

```bash
python -m pvess_calc.qet.template   # 写回 library/templates/residential-ess-v0.qet
```

修改文本布局只改 `template.py` 里的 `DEFAULT_LABELS`。修改 schema 骨架改 `PROJECT_TEMPLATE` 字符串。改完跑 `python -m pvess_calc.qet.template && pytest -q`，再用 QET 打开验证。

### Phase 1 元件 + 连线模板

`src/pvess_calc/qet/elements.py` 生成带真实 `<element>`（嵌入 `.elmt` 定义）+ `<conductor>` 连线的 QET 项目。

```bash
python -m pvess_calc.qet.elements   # 写回 library/templates/demo-elements.qet
```

### QET 0.90 schema 已踩的坑（不要再踩）

`tests/test_qet_elements.py` 把以下规则 lock 死。改 elements.py 时务必让测试继续过：

1. **`<project version="0.90">`** ——不是 `"0.80"`。版本号错了 QET 静默拒绝加载整个项目树。
2. **没有 `<?xml ... ?>` 声明** —— QET 自己保存的文件直接从 `<project>` 开始。
3. **实例端子 x 必须内缩 4px**（`_inst_x(25) == 21`，`_inst_x(-25) == -21`）。QET 按**位置**绑定实例端子到 .elmt 定义里的端子；位置不对就丢弃端子，conductor 找不到目标 → 日志报 `Diagram::fromXml: terminal id N not found`，连线静默消失。
4. **`<conductor>` 必须含 `<sequentialNumbers/>` 子节点**——自闭合 `<conductor .../>` 被 QET 忽略。
5. **元素按 x 降序排** —— QET 保存时按降序写元素，对应 terminal id 从 0 递增。生成器跟着这个顺序写 element + 算 terminal_base_id，conductor 才能精确引用。
6. **实例端子只保留 `x/y/orientation/id`** —— 加 `name=""/number=""/nameHidden="0"` 不会报错但跟 QET 输出不一致，后期 diff 会很乱。
7. **.elmt 集合里的端子保留 `name`**（`DC+`、`DC_IN+` 等）——这是给人看的标识，不影响 QET 位置绑定。

### QET CLI 的坑

不要用 `open -a /Applications/qelectrotech.app file.qet`——会触发 QET 的导出模式（log 里 `Export XML de 1 schemas`），GUI 不真正加载。正确姿势：
- 双击 .qet 文件
- 或先空启动 QET 再 File → Open
- 或命令行 `/Applications/qelectrotech.app/Contents/MacOS/qelectrotech file.qet 2>log.txt`（同时抓 stderr 看 `Diagram::fromXml` 警告）

## 命名规范

- 设备标签：`PV-1`, `DC-COMB-1`, `RSD-1`, `INV-1`, `ESS-1`, `AC-DISC-1`, `MSP`
- 文件命名：项目目录用 `NNN-customer-name`（NNN 是 3 位编号）
- 标准 OCPD 安培档：15/20/25/30/35/40/45/50/60/70/80/90/100/110/125/150/175/200/225/250/300/350/400/450/500（NEC 240.6）

## 占位符符号清单（Phase 0）

`library/symbols/v0/` 下：
- `pv_array.elmt` — PV 阵列（DC+/DC-/GND 端子；label/string_count/module_count/voc_cold/isc_max 文本槽）
- `dc_combiner.elmt` — DC 组合器/隔离（多 in / 1 out / GND；label/ocpd_rating）
- `rsd.elmt` — Rapid Shutdown Device，NEC 690.12（DC in/out；label/model）
- `hybrid_inverter.elmt` — 混合逆变器（DC/Battery/AC/GND；label/model/ac_output_a）
- `ess_unit.elmt` — 储能单元（Battery+/-/Comms；label/model/qty/kwh）
- `ac_disconnect.elmt` — AC 隔离开关（in/out/GND；label/rating_a）

Phase 1 才换精美美标 `.elmt`——届时不改 terminal 位置和 dynamic_text 名字（接口契约）。

## NEC 关键条款速查（NEC 2023）

| 条款 | 内容 | 计算公式 |
|------|------|----------|
| 690.7(A) | PV 源极冷修正 Voc | `Voc_max = Voc_stc × (1 + βVoc × (T_min - 25))` 或 Table 690.7 校正系数 |
| 690.8(A)(1) | PV 源回路电流 | `I_pvsource = Isc × 1.25` |
| 690.8(B) | PV 导体 ampacity | `I_conductor ≥ I_pvsource × 1.25` 再加 310.15 修正 |
| 690.9 | PV OCPD | `OCPD ≥ 690.8(A) × 1.25` 取下一标准档 |
| 690.12 | Rapid Shutdown | 阵列边界 1ft 外 ≤ 30V（30s）|
| 705.11 | Supply-side tap | 主开关电源侧接入，不受 busbar 限制 |
| 705.12(B)(3)(1) | Sum rule | `主开关 A + 反馈 A ≤ busbar A` |
| 705.12(B)(3)(2) | 120% rule | `主开关 A + 反馈 A ≤ busbar A × 1.2`，反馈接母线对侧 |
| 706.7 | ESS 断开装置 | 每个 ESS 单元前 |
| 706.15 | ESS OCPD | DC/AC 两侧均需 |

## 标准 OCPD 选型（240.6）

`pvess_calc.nec.v2023.STANDARD_OCPD_RATINGS` 维护。永远向上取整到下一档。

## Documentation

文档站位于 `docs/`，MkDocs Material 主题。本地预览：

```bash
pip install -e ".[docs]"
mkdocs serve                     # http://127.0.0.1:8000
mkdocs build --strict            # 一次性 strict build；CI 用同样模式
```

**自动部署**：push 到 `main` 触碰 `docs/**` / `mkdocs.yml` / `README.md`
自动 deploy 到 GitHub Pages（`.github/workflows/docs.yml`，使用官方
`actions/deploy-pages@v4` 流程，不依赖 gh-pages 分支）。

PR 路径只 build 不 deploy — 早期 catch docs 回归不污染生产站点。

First-time GH Pages 设置（一次性）：见 [`docs/deploying.md`](docs/deploying.md)
第 1-4 步。核心：

1. 替换 `mkdocs.yml` 中 `your-org` / `pvess-calc` 为真实仓库
2. **Settings → Pages → Source → GitHub Actions**
3. **Settings → Actions → General → Workflow permissions → Read and write**
4. 触发首次部署（push 或 manual workflow_dispatch）

## CI

`.github/workflows/ci.yml` 每次 push 到 main + 每个 PR 都跑：

- **pytest matrix**: Python 3.10 + 3.12（项目最低 + 最新稳定版）
- **doctor**: Phoenix + Austin 两个项目都跑 28-check 自检

doctor 在 Phoenix（features-rich）上 catch invariant 回归，在 Austin
（minimal）上 catch "skipped 路径自身坏了" 的回归。

ASCII path 注意事项：本仓库目录名含中文（`11CAD家庭储能`），导致
editable `.pth` 文件在某些 Python build 上不生效。pytest 有
`pyproject.toml` 里的 workaround（`tool.pytest.ini_options.pythonpath`），
但 console scripts 像 `pvess-doctor` 调用时仍会 `ModuleNotFoundError`。
CI 在 GitHub Actions 上跑（ASCII 路径），不受影响。本地 debug 时
临时用 `cp -r . /tmp/ascii-pvess && cd /tmp/ascii-pvess` 验证。

## Changelog

[`CHANGELOG.md`](CHANGELOG.md) — K-phase milestone 历史，倒序排，
Keep-a-Changelog 格式。`docs/changelog.md` 是它的 symlink，所以
mkdocs site 跟 root CHANGELOG 永远一致。

## 工作流图（K.7）

```
INTAKE                 DESIGN                   SUBMIT                   VERIFY
─────────              ─────────                ─────────                ─────────
pvess init             pvess calc               pvess permit             pvess doctor
pvess survey      →    pvess customer      →    pvess dxf            →   pvess symbols
pvess lookup           pvess compare            pvess labels
                                                pvess render

Pipeline shortcuts:
  pvess pipeline customer projects/<id>/   →  calc + customer-summary (sales demo)
  pvess pipeline submit   projects/<id>/   →  calc + permit + dxf + doctor (AHJ bundle)
  pvess pipeline review   projects/<id>/   →  submit + open permit PDF
```

## 命令速查

```bash
pip install -e .                              # 安装开发版
pytest -q                                      # 跑测试

# K.7 统一入口（推荐 — 旧 `pvess-*` 命令仍向后兼容）
pvess --help                                   # 看完整工作流
pvess <subcommand> --help                      # 看子命令选项

pvess calc projects/<id>/                      # NEC 计算 + Markdown 报告（旧 pvess-calc）
pvess render projects/<id>/                    # 内部评审 QET SLD（旧 pvess-render）
pvess labels projects/<id>/                    # NEC 标签 PDF（旧 pvess-labels）
pvess dxf --preview projects/<id>/             # 报批级 DXF（旧 pvess-dxf）
pvess customer projects/<id>/                  # K.4 业主友好单页 PDF（旧 pvess-customer-summary）

# 旧命令仍可用（向后兼容）
pvess-calc projects/<id>/                      # = pvess calc projects/<id>/
pvess-customer-summary projects/<id>/          # = pvess customer projects/<id>/

# Phase E: 方案对比矩阵
pvess-compare projects/<id>/scenarios/         # 跑 N 套配置 → comparison.md + .json

# Phase F+G: 完整提交包（含 AHJ 过滤）
pvess-permit --ahj phoenix_az projects/<id>/   # → permit-package-<id>.pdf
# 可选 --ahj: austin_tx / phoenix_az / california_generic / hawaii_generic

# 结构性自检（Sheet Registry 一致性、AHJ profile 完整性、PDF 可搜索、无截断切片）
pvess-doctor projects/<id>/                    # 退 1 = 有结构漂移，必须修
```

`pvess-doctor` 比 `pytest` 更聚焦——前者验跨页/跨配置不变量，后者验单元逻辑。
改 `permit/` / `dxf/` / `qet/` / Sheet Registry 后必须同时绿。

## 标准与工具

- `docs/TESTING.md` — 新功能落地必须满足的测试条件 + 已知漏报模式 + **positive-guard vs regression-bait 测试范式 (§7)**
- `docs/DESIGN.md` — NEC 多版本派发、Sheet Registry、layout 常量、schema 加性、截断 7 条铁律、design tokens (§7.5)、**schedule 表格规范 (§7.6)**
- `src/pvess_calc/permit/sheet_registry.py` — Sheet 单点真源（cover/builder/AHJ 三方都读它）
- `src/pvess_calc/permit/_textfit.py::fit()` — 按 stringWidth 截断 + 加 `…`，禁用 `text[:N]` 切片
- `src/pvess_calc/dxf/typography.py` — **DXF 4 字号 tier**（TEXT_TITLE / HEADER / BODY / CAPTION）
- `src/pvess_calc/dxf/strokes.py` — **DXF 3 线重 tier**（STROKE_THIN / MED / HEAVY）
- `src/pvess_calc/dxf/_textfit.py::fit_dxf()` — DXF 版宽度估算截断
- `.Codex/skills/pvess-review/` — 一键 rebuild + doctor + 栅格化 + 逐页 review
- `.Codex/skills/pvess-visual-polish/` — **视觉打磨迭代** playbook（收口标准、碰撞模式、修法清单）

## Doctor 自检项（pvess-doctor）

| 检查 | 覆盖 |
|---|---|
| `inputs_load` / `calc_engine` | 数据加载 + 计算引擎 |
| `ahj_profile.*` / `label_set.*` | 4 个 AHJ profile 的 sheet codes + label codes 注册 |
| `no_truncation_slices` | 禁用 `text[:N]` 切片（permit + dxf 双路径） |
| `cover_index_matches_pipeline` | 封面 SHEET INDEX 跟 builder 实际页序一致 |
| `permit_emits_registry` | builder 实际页数 ≥ registered sheets 数 |
| `pdf_text_searchable` | PDF 文字可搜（不是 image-only） |
| `dxf_text_no_overflow` | EE-1/EE-2 上 SCHEDULE/TITLE_BLOCK/NOTES 层文字不溢出容器 |
| `dxf_no_text_overlap` | EE-1/EE-2 上 TEXT 实体两两 bbox 不重叠（>25%） |
| `site_checklist_covers_schema` | site checklist 39 字段都映射到 Inputs schema |
| `subpanel_slots_sufficient` | K.2.5：每个 panel 槽位够装新 PV/ESS 反馈 |
| `lookup_offline_works_without_keys` | K.3b：缺 API key 时 lookup 仍能离线返回 ≥5 字段 |
| `customer_summary_renderable` | K.4：customer-summary PDF 无 lookup 时仍能渲染 (>= 10 KB) |
| `customer_design_tokens_respected` | K.4：PDF 字号必须用 `design_tokens.PT_*` 4 tier 之一 |
| `ess_install_compliant` | K.2.6b：NEC 706.10 / IRC R328 setbacks + 40 kWh 室内容量上限 |
| `roof_usable_area_sufficient` | K.2.6c：每个 roof_section 模块需求 ≤ 设防后 usable area |
| `grounding_electrode_system_compliant` | K.5：GEC 大小 vs NEC 250.66 + ≥2 electrodes (250.50) + main bonding jumper |
| `nec_edition_artifacts_consistent` | K.7：report.md / permit PDF 印刷的 NEC 版本 = inputs.yaml 声明的版本 |
| `export_tariff_matches_state` | K.7：CA → ca_nem3 / HI → hi_self_consumption 强制；其他州 1to1_nem PASS |
| `rsd_label_substitution_wired` | K.7：RSD 标签 `{{RSD_BOUNDARY_V}}` 占位符 + build_substitutions 接通正确（2017→80V, 2020/2023→30V） |
| `compare_pdf_renderable` | K.7：Phoenix scenarios → comparison.pdf 渲染 ≥ 2 KB 无异常 |
| `production_breakdown_per_face` | K.8：多面 roof_sections 项目必须输出 `production_breakdown`，每面 derate ∈ (0, 1]，blended ∈ (0, 1] |
| `tx_rep_plan_explicitly_chosen` | K.4.6.6：TX 项目还用 generic `1to1_nem` → WARN（提示 tx_* 预设或 `rep_buyback_ratio` 覆盖）|
| `self_consumption_realistic_for_rep_plan` | K.4.6.6：sub-1:1 REP plan + 被动 self_cons < 0.40 + 无电池 → WARN（提示 Smart Meter Texas load-shifting 可拉 self_cons 到 0.60+）|
| `face_value_score_distinguishes_east_west` | K.8.2：value-weighted math 契约。0.50× REP 下 E/W spread ≥ 8% AND 1:1 下 E ≈ W collapse ≤ 0.01。防 SC pattern 被「简化」成 flat 0.50 的回归。|
| `pv4_module_count_matches_yaml` | K.9.5：Σ PV-4 placements vs `pv_array.modules` 一致性。0% 短缺 PASS / ≤5% PASS-with-note / 5-10% WARN / >10% FAIL（roof 过载）。|
| `cover_has_governing_codes_for_ahj` | K.12.5：cover sheet GOVERNING CODES 块必须列 9 个 code（NEC + 8 个 ICC family），每个含 4 位年份。防 BuildingCodes defaults 被清空导致 AHJ 拒收。|
| `string_balance_within_target` | K.10.5：K.10 string assignment 平衡性 — `|max-min| ≤ 1` PASS / `==2` WARN / `≥3` 或 over-target FAIL。防 `_allocate_string_counts()` 回归。|
| `auto_routed_lengths_sane` | K.11.5：当 `site.equipment_locations` 触发自动布线时，任何单段 > 200 ft 一律 FAIL（住宅外包络阈值，常见的 m↔ft 单位错误或坐标系混乱守门）。|

**doctor 不覆盖的 gap**：text vs **wire/icon 几何** 碰撞。需肉眼复查（visual-polish skill §C/§D）。

## 业主友好输出 PDF（K.4）

`pvess-customer-summary projects/<id>/` 生成 `output/customer-summary.pdf`——单页 US Letter，业主能看懂的方案概览。

**4 个内容块**：
1. **系统概览** — PV 模块数 / 电池总 kWh / 逆变器 kW AC
2. **能效收益** — 月省 $ (大字号橙色) / 年省 $ / 回本年 / 年覆盖率环形图
3. **备份能力** — 仅关键负载 / 含空调 / 含冬季加热 三档 hours
4. **月度图表** — 12 月 PV 发电柱状 + 户用电叠加线（若 `monthly_kwh` 提供）

**关键依赖**：
- `lookup.resolve()` 出的 `annual_energy_kwh_per_kw`（NREL）+ `avg_residential_rate_usd_per_kwh`（K.4 utility rate dataset）
- 缺数据自动降级：无 NREL → latitude-band fallback；无 utility rate → USA-avg $0.165/kWh；无 12 月用电 → 隐藏 offset donut

**视觉收口铁律**（doctor `customer_design_tokens_respected` 守门）：
- 4 字号 tier：`PT_HERO` / `PT_TITLE` / `PT_BODY` / `PT_MICRO`（design_tokens.py）
- 2 主色：`COLOR_PRIMARY`（蓝，系统/发电）+ `COLOR_ACCENT`（橙，收益）+ 1 成功色（绿，备份）
- 2 图表类型：`bar`（月度发电）+ `donut`（覆盖率）

**新模块**：
- `src/pvess_calc/customer/economics.py` — 年发电 / 月省 / 回本计算（USA-avg fallback）
- `src/pvess_calc/customer/production.py` — **K.8** per-face 年发电聚合器（多面 derate × shading）
- `src/pvess_calc/customer/backup.py` — 备份小时数（critical sub-panel + HVAC 分场景）
- `src/pvess_calc/customer/design_tokens.py` — 字号 / 配色 / 图表类型集中
- `src/pvess_calc/customer/charts.py` — matplotlib 出 PNG (donut + bar)
- `src/pvess_calc/customer/pdf.py` — reportlab 整合（K.8 起多面项目加 "Production by roof face" 表）
- `src/pvess_calc/calc/orientation.py` — **K.8** Sandia 30°-45° 纬度的 azimuth/tilt derate 表 + 双线性插值；`urban_density` 默认 shading（rural 1.00 / suburban 0.96 / urban 0.90）
- `src/pvess_calc/lookup/data/utility_rate.json` + `providers/static_utility_rate.py` — 30 城市住宅 $/kWh

**K.8 数据契约**：
- `Site.urban_density: Literal["rural", "suburban", "urban", "unknown"]`（默认 `"unknown"`）
- `RoofSection.shading_factor: float = 1.0`（< 1.0 视为人工测量值；== 1.0 走 density 默认）
- `EconomicsResult.production_breakdown: list[FaceProduction]`（单面项目为空）
- `EconomicsResult.production_blended_derate: Optional[float]`（单面项目 None）
- 单面项目向后兼容：`pv_array.modules × per_kw` bit-identical 到 K.7 之前。

**K.8.1 K.3c × K.8 衔接（2026-05-16 修复）**：

`ProductionResult.method` 三态：
- `"per_face"` — designer 手工把 `pv_array.modules` 分配进各 `section.module_count`
- `"per_face_auto_distributed"` — K.3c-init 状态（sections 来自 Google Solar 但所有 `module_count=0`），engine 按 `gross_area_sqft` 比例自动分。守恒规则：最后一面拿 remainder，`Σ face_modules == pv_array.modules` 精确。
- `"system_aggregate"` — 无 sections 或所有 sections area=0 时的 legacy 单朝向兜底

`ProductionResult.is_per_face` 对前两种都返回 True——customer PDF / doctor check 一视同仁。

doctor `production_breakdown_per_face` 三态：
- 无 sections → PASS "single-orientation"
- sections + `pv_array.modules=0` → PASS "no PV declared"
- sections + PV → 必须输出 breakdown；如果是 auto-distributed 路径，PASS detail 会带 "(auto-distributed by area — designer review recommended)" 提醒工程师 submit AHJ 前 review 分配方案

`wizard/runner.py` 通过 `__k3c_roof_sections` magic key 把 K.3c list payload 从 `_prefill_from_address` 传给 `run_wizard`，在 `_post_process` 之后、`_validate_and_write` 之前注入到 `nested.site.roof_sections`。LOOKUP_FIELD_TO_YAML_PATH 仍是 scalar-only 映射，list 走 side channel。

## 地址查询服务（K.3）

`pvess-init --address "<addr>"` 调用 `pvess_calc.lookup.resolve()` 把地址变成预填默认值。

**离线 provider（K.3a，零配置）**：
- `static_ashrae` → `ashrae_2pct_min_c`, `ashrae_2pct_max_c`（~35 城市）
- `static_utility` → `utility_name`, `utility_territory_type`
- `static_ahj` → `ahj_name`, `permit_portal`
- `static_climate` → `iecc_climate_zone`（state + city override）
- `static_nec` → `nec_edition`（state default）

**在线 provider（K.3b / K.3c，需 env var）**：
```bash
export PVESS_MAPBOX_TOKEN="pk.your_public_token"   # https://account.mapbox.com/access-tokens/
export PVESS_NREL_API_KEY="your_developer_key"     # https://developer.nrel.gov/signup/
export PVESS_GOOGLE_SOLAR_KEY="AIza..."            # https://console.cloud.google.com/apis/library/solar.googleapis.com
```
- `mapbox_geocode` → `latitude`, `longitude`, `county`, `canonical_address`
- `nrel_pvwatts` → `solar_irradiance_kwh_m2_day`, `annual_energy_kwh_per_kw`
- `google_solar` （K.3c）→ `roof_sections[]`（per-face pitch / azimuth / area，对应 K.2.6c schema）+ `google_solar_imagery_date` + `google_solar_imagery_quality`（HIGH/MEDIUM/LOW → high/medium/low confidence）+ `google_solar_max_panels` + `google_solar_whole_roof_area_m2`。**替代 $20-40 EagleView 报告**做 calc-engine path。同 `nrel_pvwatts` 一样依赖 mapbox 出 lat/lng。

key 缺失时 online provider 返回 `confidence='miss'`，offline 链不受影响。任何 HTTP 异常（超时 / 4xx / 5xx / 404 building-not-found）都被 `resolve()` 的 try/except 兜住。结果缓存 24h 在 `~/.pvess/cache/lookup/<sha>.json`，跨 provider chain 自动 invalidate。

**K.3c 已知 limitation**：
- Google Solar 只返回 axis-aligned bounding box，没有 K.2.7 polygon vertices——hip / L-shape 屋面近似成同面积正方形。复杂屋面 submit 阶段仍可用 EagleView 18-page PDF 作附件。
- 联排 / 双拼偶尔返回邻居 building；用 mapbox 的 canonical_address vs Google 返回 center 对比验证。
- imagery quality LOW 时 confidence 强制降为 low（wizard 会标 REVIEW-ME 而不是 silent-assume）。

## 阶段总览

| Phase | 内容 | 关键模块 | 状态 |
|-------|------|----------|---|
| 0-1.5 | NEC 计算 + QET SLD + 标签 PDF | `calc/`, `qet/`, `labels/` | ✅ done |
| 2 (B/C/A) | DXF 三线图 + 接地图 + 真符号 | `dxf/render.py`, `dxf/grounding_sheet.py` | ✅ done |
| D | 真实压降 / AIC / 设备库 / 温度修正 / NEC 多版本 | `calc/voltage_drop.py`, `calc/aic.py`, `devices/`, `nec/v2020.py` | ✅ done |
| E | 方案对比矩阵 + BOM | `compare/` | ✅ done |
| F | 完整 7 页报批 PDF（cover/EE-1..5/labels） | `permit/builder.py`, `permit/*.py` | ✅ done |
| G | AHJ profile 系统 | `ahj/profiles/*.yaml` | ✅ done |
| K.1 – K.8.1 | site checklist / wizard / lookup / customer PDF / GES / NEC 三版本 / per-face derate / K.3c × K.8 自动分配 | (见各 K.x 块) | ✅ done |
| K.3c+ | Google Solar `dataLayers` 卫星图 + flux 叠加（tier-gated） | `customer/roof_satellite.py` | ✅ done |
| K.8.1 v2 | Largest Remainder Method 模块分配（Frisco E2E 暴露的 last-face-zero bug） | `customer/production.py` | ✅ done |
| K.4.6 | Equipment library + cost overrides + battery-optional + TX REP picker + SMT-aware checks + 3-tier quote table | `devices/`, schema cost-override block, `customer/economics.py`, `customer/quote_tiers.py`, `customer/pdf.py`, doctor `tx_rep_plan_explicitly_chosen` + `self_consumption_realistic_for_rep_plan` | ✅ done (2026-05-17) |
| K.8.2 | Value-weighted orientation derate（TX 下午峰 + REP buyback 加权 → 自动化 SW-quadrant 偏好；opt-in `use_value_weighted_distribution` flag） | `calc/value_weighted.py`, `customer/production.py` LRM 切换, doctor `face_value_score_distinguishes_east_west` | ✅ done (2026-05-17) |
| K.9 | Per-module layout 引擎 + PV-4 v2（Aurora-grade attachment plan，含 module dimension callout） | `calc/module_placement.py`, `calc/face_distribution.py`（共享 LRM）, `permit/structural.py` v2, doctor `pv4_module_count_matches_yaml` | ✅ done (2026-05-17) |
| K.12 | Industry-standard PV-1 cover page（Wyssling-style 12 块布局 + aerial/vicinity 地图 + governing codes / design criteria / roof info / meter info / revision history） | `permit/cover_sheet.py` v2, `permit/cover_maps.py`, schema RoofInfo/BuildingCodes/DesignCriteria/MeterInfo/RevisionEntry, doctor `cover_has_governing_codes_for_ahj` | ✅ done (2026-05-17) |
| K.10 | String-level layout + EE-1 string overlay（每模块 string_index + PV-4 色带 + 平衡 doctor 检查）| `calc/string_assignment.py`, `permit/structural.py`, doctor `string_balance_within_target` | ✅ done (2026-05-17) |
| K.11 | Wire trunk auto-routing（站点坐标 → 5 段 Manhattan 导线长度 + EE-4 polyline overlay）| `calc/wire_routing.py`, schema `EquipmentLocations` + `RoofSection.site_anchor`, `permit/site_plan.py` overlay, doctor `auto_routed_lengths_sane` | ✅ done (2026-05-17) |
| **H** | **DC AFCI / SPD / 接地极 / Conduit fill** | `calc/adjacent.py` | 📋 **NEXT** — 见 `ROADMAP.md`（3 天）|
| I | NEC 2017 + CA Title 24 + HI Rule 14H + TX Oncor | `nec/v2017.py`, `regional/*` | 📋 planned |

**`ROADMAP.md`** 维护所有 planned / backlog 阶段的详细 sub-task 拆分、收口标准、工作量估计。当一个 K-phase 落地，把它从 ROADMAP 移到 CHANGELOG。

## inputs.yaml 可选块（Phase B 起）

```yaml
project:
  client_name: "Hollow Hill Residence"
  site_address: "2500 Hollow Hill Lane, Lewisville, TX"
  coordinates: "33.035, -96.902"
  apn: "R-..."
  utility: "COS"
  drawn_by: "SVP"
  revision: "B"
  initial_design_date: "2025-10-06"

design_engineer:
  firm: "Wyssling Consulting"
  address: "76 N. Meadowbrook Drive, Alpine UT 84004"
  contact_email: "swyssling@wysslingconsulting.com"
  contact_phone: "(201) 874-3483"
  firm_number: "20109"

installer:
  company: "Texas Green Eco Power"
  address: "2806 Green Cir Dr, Mansfield, TX"

service:
  # ... main_panel_a / busbar_a / interconnection_methods unchanged ...
  sub_panels:
    - name: "Sub Panel #2"
      rating_a: 200
      busbar_a: 200
      location: "NW exterior wall"
      backfeed_breaker_a: 50
    - name: "Sub Panel #1"
      rating_a: 200
      busbar_a: 200
      backfeed_breaker_a: 150
```

字段全部可选。旧 yaml（如 Smith Residence）继续工作，title block 里相应字段显示 "—"。

## inputs.yaml Phase K.2.5 可选块（多 PV / panel slots / 户用电量）

```yaml
service:
  # ── 既有 PV/ESS 反馈电流（NEC 705.12 多 PV bus-load 原则）──────────
  existing_solar_breaker_a_msp: 25          # 已在 MSP 上的 PV/ESS 反馈断路器
  msp_available_slots: 30                   # MSP 总槽位（铭牌）
  msp_used_slots: 26                        # MSP 已占用槽位（4 free）

  sub_panels:
    - name: "Sub Panel #1"
      rating_a: 200
      busbar_a: 200
      existing_solar_breaker_a: 40          # 该 sub-panel 已装的 PV/ESS 反馈
      available_slots: 40
      used_slots: 36                        # 4 个空位
      service_rated: false                  # NEC 230.71 service disconnect?
      enclosure_rating: "NEMA 1"            # NEMA 1 / 3R / unknown

loads:
  # ── 户用电量（sizing 参考；不影响 NEC 校核）──────────────────────────
  monthly_kwh: [820, 740, 690, 780, 1020, 1350,
                1480, 1520, 1380, 1010, 760, 790]   # 12 月 oldest first
  hvac_type: "heat_pump"                  # heat_pump / gas_furnace_ac / electric_resistance / unknown
  has_ev: true
  planned_ev: false
  planned_electrification: false          # 计划加热泵 / IH / HPWH
```

**算法影响**：
- `service.total_existing_solar_a = existing_solar_breaker_a_msp + Σ sub_panels[].existing_solar_breaker_a`
- 705.12 sum/120% rule：`main + new_backfeed + existing_solar ≤ busbar [× 1.20]`
- doctor `subpanel_slots_sufficient`：`available_slots − used_slots ≥ 2`（一个 2-pole 反馈断路器）
- 报告 §0 "户用电量参考" 仅在 `monthly_kwh` 长度=12 时渲染

**加性兼容铁律**（K.2.5 锁定）：
- 旧 yaml 不动也 PASS：所有新字段 `default=0 / [] / "unknown" / False`
- `existing_solar_breaker_a* = 0` → 算法走老分支，报告 §2 不出现"既有反馈"行
- `available_slots = 0` → doctor 视为"未知"，PASS with note

## inputs.yaml Phase K.2.6 可选块（现场拓扑细化）

```yaml
service:
  sub_panels:
    - name: "Sub Panel #1"
      rating_a: 200
      busbar_a: 200
      # K.2.6a: 入站走线长度（从 AC-DISC 或上一个 sub-panel 到这一面）
      distance_to_msp_ft: 22.0

battery:
  # K.2.6b: ESS 物理安装位置
  install_location: "garage"   # indoor / garage / outdoor / outdoor_protected / unknown
  distance_to_doorway_ft: 4.5  # 距门 ≥3 ft (IRC R328.5)
  distance_to_window_ft: 6.0   # 距窗 ≥3 ft
  distance_to_egress_ft: 5.0   # 距 egress ≥3 ft (IRC R328.4)
```

**算法影响**：
- `voltage_drop`：sub_panel chain → AC trunk 拆成 D1/D2/.../Dn 多段，每段独立算 drop
- `calc/ess_install.py`：NEC 706.10 + IRC R328 校验
  - indoor / garage：3 ft setback × 3 + 40 kWh capacity ceiling
  - outdoor / outdoor_protected：跳过 R328，只走 706.10 disconnect 提示
  - unknown：WARN（不 FAIL），doctor 退 0 但提示补数据

**加性兼容铁律**：
- 旧 yaml：每个 sub_panel 的 distance_to_msp_ft=0 → fallback 到单段 "D · AC-DISC→MSP"（bit-identical 历史输出）
- 旧 yaml：battery.install_location='unknown' → 单条 WARN 检查，doctor 仍 PASS

## inputs.yaml Phase K.2.6c 可选块（屋顶几何 + 障碍物）

```yaml
site:
  roof_sections:
    - name: "South Gable"
      roof_type: "Comp Shingle"
      pitch_deg: 22
      azimuth_deg: 180
      width_ft: 42                    # rect 宽 / tri 底边
      height_ft: 18                   # rect 高 / tri 斜高
      module_count: 30
      shape: "rect"                   # rect / tri
      apex_x_ratio: 0.5               # 仅 tri：顶点位置 (0=左, 0.5=居中)
      default_setback_ft: 1.5         # NEC 690.12 默认 18"
      edge_setbacks:                  # 覆盖某条边的 setback
        - edge_type: "eave"           # eave / ridge / rake / valley / hip / apex
          setback_ft: 3.0             # CA Title 24 大屋檐 setback
      obstructions:                   # 烟囱 / 天窗 / 通风口
        - kind: "chimney"             # chimney / skylight / vent_pipe /
          x_ft: 8                     #   hvac_unit / fan_vent / access_hatch /
          y_ft: 10                    #   satellite_dish / other
          width_ft: 3
          height_ft: 3
          setback_ft: 1.5             # 周围净空
      obstructions_note: ""           # site surveyor 用，free-text 备注

    - name: "West Hip"
      shape: "tri"
      width_ft: 28                    # 三角形底边
      height_ft: 14                   # 三角形斜高
      apex_x_ratio: 0.5               # 等腰三角形（多数 hip 屋面）
```

**算法影响**：
- `calc/roof_layout.py`：每个 section 算 gross / setback_loss / obstruction_loss / usable_area
  - 矩形：每条边 inset 后矩形面积 − 障碍物 halo 矩形面积
  - 三角形：inradius-shrink 公式 `A' = A × ((r-d)/r)²` 其中 r = 2A/P
- doctor `roof_usable_area_sufficient`：`module_count × 22 sqft ≤ usable_area`，否则 FAIL "over-packed"
- PV-4 attachment plan：表格新增 SHAPE / GROSS / USABLE 列；底部 ROOF SECTION PLANS 绘制矩形/三角形 outline + 虚线 setback + 橙色 hatch 障碍物 + 模块 grid

**加性兼容铁律**：
- 旧 yaml 无 `shape` → 默认 "rect"；无 `obstructions` → 空 list
- `default_setback_ft = 1.5` 默认值匹配 NEC 690.12 → 旧 yaml usable area = inset rect area
- 三角形面尚不绘制 module grid（K.2.7 待办）；其他章节渲染正常

## inputs.yaml Phase K.2.7 可选块（多边形屋面）

```yaml
site:
  roof_sections:
    - name: "South L-Roof"
      shape: "polygon"          # K.2.7: rect / tri / polygon
      pitch_deg: 22
      azimuth_deg: 180
      # CCW vertices in section-local ft. Origin = eave-left corner;
      # +x along eave, +y toward ridge / apex. Must form a simple
      # (non-self-intersecting) polygon. ≥3 vertices required.
      vertices:
        - [0, 0]
        - [30, 0]
        - [30, 10]
        - [40, 10]
        - [40, 30]
        - [0, 30]
      # width_ft / height_ft still required (used by PV-4 bbox fallback
      # + site_checklist); vertices override them for area math.
      width_ft: 40
      height_ft: 30
      module_count: 24
      attachment_count: 32
```

**算法影响**：
- `RoofSection.gross_area_sqft` 走 shoelace 公式（精确）
- `roof_layout._polygon_usable_after_setbacks()` 走 Minkowski 公式：
  `A' = A − d·P + π·d²`（凸多边形精确，凹多边形 O(d²) 保守低估）
- `calc/polygon.py` 提供 `polygon_area` / `polygon_inset_area` / `point_in_polygon` / `is_convex` / `clipped_grid` / `offset_polygon` / `fit_module_grid` 基础操作
- PV-4 渲染（K.2.8 升级）：
  - **凸 + 凹多边形**（L / T / cross / pent）→ outline + per-vertex bisector dashed inset + `fit_module_grid` 二分搜索 cell size 准确放 N 个模块
  - K.2.7 known-limits（凹形 inset 交叉、模块数低估）→ **K.2.8 全部修复**
- pydantic validator 在 model load 强制：≥3 顶点 / 简单（不自交） / CCW
- 自检顺序：先 self-intersect 再 CCW，因为 bowtie 多边形签名面积可能为 0 而错误 trigger CCW 警告
- **per-vertex bisector offset 公式**（凸凹通吃）：
  ```
  V' = V + (n_prev + n_next) × d / (1 + n_prev · n_next)
  ```
  其中 n_prev / n_next 是相邻边的内向单位法线。分母 < 0.05 时 clamp 防止退化。
- **fit_module_grid 二分搜索**：8-10 次迭代收敛到 ±0.05 ft 精度，找到能容纳 ≥ N 模块的最大 cell size（最稀疏 = 视觉最清楚）

**加性兼容铁律**：
- 旧 yaml（仅 rect/tri）继续工作；`shape="polygon"` 是 opt-in
- 旧 RoofSection 默认 `shape="rect"`，`vertices=[]`
- pydantic validator 在 `shape != "polygon"` 时跳过 vertices 检查

## inputs.yaml Phase K.5 可选块（接地系统现状）

```yaml
service:
  grounding_electrode_system:
    # 实际接地极 — 0..N 根 (NEC 250.52(A)(5))
    rods:
      - length_ft: 8
        diameter_in: 0.625      # 5/8" 最常见
        material: "copper_clad_steel"
        location: "SE corner of garage"
      - length_ft: 8
        location: "6 ft NE of rod #1"   # NEC 250.53(A)(3) 间距 ≥6 ft
    # 金属水管 — 仅当确认是 metal 且 underground ≥10 ft 才合格
    metal_water_pipe:
      bond_size_awg: "6"
      underground_length_ft: 12
      confirmed_metal_underground: true   # PEX-replaced → false
      location: "basement service entry"
    # Ufer / concrete-encased — 新房常见 (NEC 250.52(A)(3))
    ufer:
      length_ft: 20
      conductor: "rebar"        # "rebar" / "copper"
      conductor_size: "1/2 in rebar"
      location: "south foundation"
    # 现有主 GEC 线径 (engine 跟 NEC 250.66 要求对比)
    gec_main_size_awg: "4"      # ""=未知; 老房子常见 "8"
    # NEC 250.24 主中性点-接地 bonding
    bonded_to_neutral_at_service: "yes"   # "yes" / "no" / "unknown"
    pv_separate_ground: false             # NEC 690.47 独立打地（不推荐）
    # 给现场调研用的 free-text 备注
    existing_grounding_summary: ""
```

**算法影响**：
- `compare_gec_to_required(actual, required)` → `GecComparison` 返回 PASS / UNDERSIZED / UNKNOWN
- `GroundingResult.actual_electrodes` 列出真实安装的电极（PEX water pipe 不计）
- `GroundingResult.electrode_summary` 优先 actual_electrodes，否则 fallback 历史 3-electrode 默认
- doctor `grounding_electrode_system_compliant`：
  - UNDERSIZED GEC → FAIL
  - 仅 1 rod 且无其他电极 → FAIL（NEC 250.53(A)(2) 要求 2 rods 或 ≤25 Ω 测试）
  - `bonded_to_neutral_at_service = "no"` → FAIL
  - `"unknown"` → WARN-but-PASS
- EE-2 DXF：条件渲染 ACTUAL 电极（不画 phantom Ufer）+ GEC label 显示 actual vs required

**加性兼容铁律**：
- 旧 yaml（无 `grounding_electrode_system` 块）→ `bonded_to_neutral_at_service="unknown"` + 空 lists → doctor PASS "no GES data on file"，EE-2 走 legacy 3-electrode 默认（bit-identical 历史输出）

## inputs.yaml Phase D 可选块（工程硬化）

```yaml
pv_array:
  # 用 device library 短引用代替 inline datasheet
  module_ref: "talesun_tp7g54m_415"      # 见 src/pvess_calc/devices/modules.py

battery:
  ref: "tesla_powerwall_3"               # 同上 batteries.py

inverter:
  ref: "megarevo_r8klna"                 # 同上 inverters.py
  quantity: 3                            # 项目特定字段保留

service:
  utility_transformer:
    kva: 25                              # 服务变压器规格（用于 NEC 110.24 AIC）
    impedance_pct: 2.0
    secondary_voltage: 240
  default_ocpd_aic_ka: 10                # 住宅断路器标准 10kAIC

wire_lengths:                            # NEC 215.2 / 210.19 真实压降
  pv_string_one_way_ft: 60
  pv_to_combiner_ft: 15
  combiner_to_inverter_ft: 25
  inverter_to_ac_disc_ft: 8
  ac_disc_to_msp_ft: 12
  ess_to_inverter_ft: 5

routing:                                 # NEC 310.15(B) 温度/捆扎修正
  ambient_temp_c: 45
  pv_conduit_fill_count: 6
  ac_conduit_fill_count: 3
```

## NEC 多版本（K.7 三版本真实派发）

`inputs.project.nec_edition` 接受 `"2023" | "2020" | "2017"`：
- **2023**（默认）：120% rule + sum rule 都可用；RSD ≤ 30V
- **2020**：sum_rule 互联法被标记 `N/A · removed in NEC 2020 cycle`；RSD ≤ 30V
- **2017**：sum_rule 仍合法（PASS/FAIL 而非 N/A）；RSD ≤ 80V

规则代码：`src/pvess_calc/nec/v2023.py` / `v2020.py` / `v2017.py`。engine 通过
`get_rules(edition)` 派发；未知 edition 走 2023（最保守）。

**K.7 新增的版本差异**：
- `RSD_BOUNDARY_VOLTAGE_LIMIT` 常量从 v2017 (80V) → v2020/v2023 (30V) 阶梯
- 该常量被 `qet.inject.build_substitutions()` 读出，作为 `{{RSD_BOUNDARY_V}}` 注入
  到 `labels/specs.py` 的 RSD 标签 body — PDF 印出来的标签电压阈值跟选择的
  NEC 版本一致。

## NEC 标签 PDF（Phase 1.5）

`src/pvess_calc/labels/` 包：
- `specs.py` — 标签**数据**（NEC 条款、severity、模板字符串、`applies()` 谓词）。无渲染逻辑。
- `render.py` — reportlab PDF 输出。US Letter 2×3 网格、ANSI Z535.4 配色（DANGER 红、WARNING 橙、CAUTION 黄、NOTICE 蓝、PLAIN 灰）。

加新标签：在 `LABEL_CATALOG` 里 append 一个 `LabelSpec`。body 文本里写 `{{KEY}}` 占位符（必须在 `pvess_calc.qet.inject.build_substitutions` 里有对应键）。`applies(result)` 决定是否对当前项目输出（默认 always）。互联方法相关的标签用 `_interconnect_is("120%_rule" / "supply_side_tap")` 谓词。
