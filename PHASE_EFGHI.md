# Phase E-F-G-H-I 收口标准

总目标：把 pvess-calc 从"单项目工程工具"扩展成"商用化设计 + 报批 + 多区域支持的全栈工具"。

---

## Phase E — 方案对比矩阵 + BOM

### 范围
- 新增 `pvess-compare` CLI，输入一个 scenarios 文件夹，输出对比报告
- 项目结构：`projects/<id>/scenarios/{A,B,C}/inputs.yaml`，scenarios 内每个子目录是独立配置
- 自动跑每个 scenario 的完整计算，提取关键指标，生成对比表
- BOM：device library 加 `unit_price` 字段，每个 scenario 算总成本估算

### 完成判定
- [ ] `src/pvess_calc/compare/` 包：`scenarios.py` 读取 + `report.py` 渲染
- [ ] `pvess-compare projects/<id>/scenarios/` CLI 命令
- [ ] 输出 `comparison.md`：对比表（DC kW、AC kW、kWh、backfeed A、互联方式、AC OCPD、AIC 余量、Voc 冷、Vd %、估算 $$）
- [ ] 输出 `comparison.json`：机器可读完整数据
- [ ] `src/pvess_calc/devices/` 三个模块都加 `unit_price_usd` 字段
- [ ] BOM 计算包含：模块、逆变器、电池、AC/DC 隔离、估算线材、估算 conduit、五金/标签包（固定金额）
- [ ] ≥3 个测试：scenario 加载 / 对比表生成 / BOM 计算

---

## Phase F — 完整报批 PDF 包

### 范围
- 新增 `pvess-permit` CLI，输出单个 PDF 包含所有 sheets + 文档
- 4 个新 sheet 生成器：
  - **Cover sheet (EE-0)**：项目元信息、工程师印章位、目录索引
  - **EE-3 Panel schedules**：每个面板（MSP + 各 sub-panel）的断路器位置表
  - **EE-4 Site plan**：房屋平面 + PV 阵列朝向 + 设备位置（简化版）
  - **NEC compliance checklist**：单页核查清单（含每条 NEC 条款 PASS/FAIL）
- PDF combine：DXF→PDF 转换 + reportlab 文档拼合

### 完成判定
- [ ] `src/pvess_calc/dxf/cover_sheet.py`：封面 DXF
- [ ] `src/pvess_calc/dxf/panel_schedule.py`：EE-3 面板表 DXF
- [ ] `src/pvess_calc/dxf/site_plan.py`：EE-4 站点图 DXF（基础占位版，从 yaml 读阵列尺寸/朝向）
- [ ] `src/pvess_calc/report/compliance.py`：NEC checklist Markdown + PDF
- [ ] `inputs.yaml` 扩展 `site:` 块（roof_pitch, azimuth, array_dimensions）
- [ ] `pvess-permit` CLI 命令
- [ ] 输出 `permit-package-{id}.pdf` 单一文件，约 6-8 页
- [ ] ≥5 个测试

---

## Phase G — AHJ profile 系统

### 范围
- 不同 AHJ 要求不同 sheets/labels/forms
- 把 AHJ 抽象为可配置 yaml profile
- `pvess-permit --ahj <name>` 按 profile 输出

### 完成判定
- [ ] `src/pvess_calc/ahj/` 包，含 `profiles/` 子目录
- [ ] ≥4 个内置 profile：`austin_tx.yaml`、`phoenix_az.yaml`、`california_generic.yaml`、`hawaii_generic.yaml`
- [ ] 每个 profile 包含：required_sheets、label_set、inspector_checklist、form_blanks
- [ ] `pvess-permit --ahj austin_tx` 按 profile 过滤输出
- [ ] Profile schema 用 pydantic 校验
- [ ] ≥4 个测试

---

## Phase H — 邻近工程计算

### 范围
- 补 NEC 还没覆盖的工程计算项

### 完成判定
- [ ] **NEC 690.11 DC AFCI**：校验逆变器是否声明 AFCI 集成（inverter datasheet 加 `has_dc_afci` 字段）
- [ ] **NEC 690.12 + 285 Surge Protection**：选 SPD 类型，根据系统位置（屋顶/室内）
- [ ] **NEC 250.53(A)(2) 接地极电阻**：≤25Ω 单极 / 双极 8ft 间距校验，从 inputs 读地极数
- [ ] **NEC Ch 9 Table 4/5 Conduit fill**：根据导线数 + 尺寸算最小 conduit 尺寸（替代当前硬编码 3/4" EMT）
- [ ] 每项加 report.md 章节 + DXF schedule 适配
- [ ] ≥8 个测试

---

## Phase I — 多区域 / 法规扩展

### 范围
- 区域差异化规则集

### 完成判定
- [ ] **NEC 2017 完整规则集**（`nec/v2017.py`）：含 sum rule、80V RSD 阈值（vs 2020 的 30V）
- [ ] **CA Title 24 / CalGreen 最小子集**：`regional/california.py`，标记 PV mandate / battery-ready 要求
- [ ] **TX 单一 utility 表格模板**：Oncor solar interconnection cover letter（reportlab PDF）
- [ ] **HI Rule 14H interconnection stub**：基础互联校验扩展
- [ ] `inputs.yaml` 可选 `regional:` 块声明额外区域要求
- [ ] ≥4 个测试

---

## 全局收口

- [ ] 所有测试通过（target: ≥120）
- [ ] Smith Residence + Phoenix 两个项目跑通完整新工作流（compare / permit / ahj）
- [ ] CLAUDE.md 更新所有新命令、新 yaml 字段、新 device 字段
- [ ] 两个项目分别用 `pvess-permit` 出完整 PDF 包
