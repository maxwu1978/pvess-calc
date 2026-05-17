# Phase D — 工程硬化收口标准

目标：把工具从"演示级"升级到"可商用"——消除现有计算引擎里"开发者方便、用户会被坑"的简化假设。

## 1. 真实压降（NEC 215.2 / 210.19 / 690 informational）

### 范围
- inputs.yaml 新增 `wire_lengths:` 可选块（缺失则回退到当前 50ft 默认）
- 字段：`pv_string_one_way_ft`、`pv_to_combiner_ft`、`combiner_to_inverter_ft`、`inverter_to_ac_disc_ft`、`ac_disc_to_msp_ft`、`ess_to_inverter_ft`
- 计算每段 V drop %，含 DC 和 AC（AC 用相电压）
- NEC 限值校验：
  - DC source/feeder 段 ≤ **2%**
  - AC feeder 段 ≤ **3%**
  - 端到端 PV-to-MSP ≤ **5%**
- 任一段 FAIL 在 report.md 显著 flag，DXF schedule 增加 VD% 列

### 完成判定
- [ ] `pvess_calc/calc/voltage_drop.py` 新模块独立可测
- [ ] `VoltageDropResult` 加入 `CalculationResult`
- [ ] report.md 新增 §"压降表" 6 段 + 总计
- [ ] DXF schedule 加 VD% 列
- [ ] ≥4 个 unit test（短 run PASS、长 run FAIL、缺省回退、端到端汇总）

## 2. 设备型号库（datasheet 系统）

### 范围
- 新增 `pvess_calc/devices/` 包，含 `modules.py`、`inverters.py`、`batteries.py`
- 最少入库：
  - **3 个模块**：Talesun TP7G54M-415、Canadian Solar HiKu7、REC Alpha Pure 410
  - **3 个逆变器**：Sol-Ark 12K、Megarevo R8KLNA、Tesla Powerwall 3
  - **3 个电池**：Tesla PW3、EG4 LifePower4 V2、FranklinWH aPower
- 每条 datasheet 是 dataclass，含所有 schema 需要的字段
- inputs.yaml 支持 `module_ref: "talesun_tp7g54m_415"` 引用（query → 自动展开）；同时保留 inline datasheet 模式（向后兼容）
- 未知 ref 报错并列出可用清单

### 完成判定
- [ ] 3 个 datasheet 文件入库
- [ ] schema 支持 `*_ref` 字段，loader 解析后填回 `pv_array.module` / `battery` / `inverter`
- [ ] 现有两个项目（Smith / Phoenix）改用 ref 引用，效果一致
- [ ] ≥4 个 unit test（已知 ref OK / 未知 ref 报错 / inline 仍工作 / 字段完整）

## 3. AIC 短路额定校验（NEC 110.24）

### 范围
- inputs.yaml 新增 `service.utility_transformer:` 可选块：`kva`、`impedance_pct`、`secondary_voltage`
- 缺失时使用保守默认（25 kVA, 2% Z, 240V）≈ ~5.2 kA available fault current
- 计算 service entrance 处的 available fault current `I_sc`
- 每个 OCPD 选型时验证其 AIC ≥ I_sc
- 默认 OCPD AIC：10 kAIC（住宅常见 QO/Homeline），可在 yaml 覆盖
- report.md 新增 §AIC 校验段，含 I_sc 计算 + 每个 OCPD 的 AIC headroom

### 完成判定
- [ ] `pvess_calc/calc/aic.py` 新模块
- [ ] `AicResult` 含 `available_fault_current_a` + per-OCPD pass/fail
- [ ] yaml schema 扩展 + 默认值
- [ ] report.md 新增 AIC 段
- [ ] ≥3 个 unit test（典型住宅 PASS、大变压器近端 FAIL、缺省值）

## 4. 温度 / 捆扎修正（NEC 310.15(B)(2)(a) + (3)(a)(1)）

### 范围
- NEC Table 310.15(B)(2)(a) 温度修正系数（30°C 基准，不同温度 0.58–1.20）
- NEC Table 310.15(B)(3)(a)(1) 多导体捆扎修正（4–6 根 0.80、7–9 根 0.70 等）
- inputs.yaml 新增 `routing:` 可选块：`ambient_temp_c`、`pv_conduit_fill_count`、`ac_conduit_fill_count`
- 缺省：30°C、3 导体（不修正）
- 在 `select_copper()` 里 apply 修正系数到 ampacity 后再做选径
- report.md 显示修正系数和最终 derated ampacity

### 完成判定
- [ ] NEC 310.15 表加进 `nec/tables.py`
- [ ] `select_copper()` 接收修正系数参数，先 derate 再比较
- [ ] schema 扩展
- [ ] report.md 显示修正系数
- [ ] ≥4 个 unit test（高温 45°C 降 ampacity、6 根捆扎降 20%、组合修正、缺省不变）

## 5. NEC 2020 多版本支持

### 范围
- 新增 `pvess_calc/nec/v2020.py`
- 关键差异（vs 2023）：
  - **690.12 RSD**：2020 阵列边界 1 ft 外 ≤ 30V（2017 是 80V）；2023 增加 module-level rapid shutdown 强制
  - **705.12(B)(3)(1) sum rule**：2020 删除（2017 还在），所以候选方法应跳过
  - 表格常数（120% factor 等）2023/2020 一致
- engine.run() 根据 `inputs.project.nec_edition` 字符串 dispatch
- report.md / DXF title block 已经显示 NEC 版本，验证两版输出有可见差异

### 完成判定
- [ ] `nec/v2020.py` 实现且 v2023 不动
- [ ] engine 通过 `nec_edition` 选模块
- [ ] Phoenix 项目跑 2023 vs 2020 报告差异：sum_rule 在 2020 不被推荐
- [ ] ≥3 个 unit test（版本 dispatch、2020 sum_rule 跳过、2017 退回 fallback）

## 全局收口

- [ ] 所有测试通过（target: ≥87 个）
- [ ] Phoenix 项目跑通：`pvess-calc + render + labels + dxf --preview`
- [ ] Smith Residence 跑通同样的命令
- [ ] CLAUDE.md 更新（命令速查 + 新 yaml 字段示例）
- [ ] 报告里能看到：压降表、AIC 校验、温度/捆扎修正系数、NEC 版本字段
