# Agentic 实验结果汇总：calib 在 held-out 上 ≥ nowmc 的域

> 最后更新：2026-06-17
> 项目：WorldCalib
> 范围：agentic 域两臂消融（**calib** = self-distill 世界模型校准 + frame-audit 三断路器；**nowmc** = 无校准对照）。
> 只收录 **calib 冠军在 held-out 上 ≥ nowmc 冠军** 的域；autolab 目前仅有 train，单列。

---

## 一、总览（冠军对冠军，held-out）

通用配置：proposer = `claude-kimi-k2.7`（max effort），target = `deepseek-v4-flash`，评估温度 0.0；autolab 例外（proposer = `claude-opus-4.8` native）。

| 域 | held-out 集 | seed | calib seed→冠军 | nowmc seed→冠军 | **calib − nowmc** |
|----|------------|------|----------------|----------------|------------------|
| **GAIA (L1+L2)** | 99 | 0.29 | 0.293 → **0.495** | 0.283 → 0.343 | **+0.152** |
| **tau2 banking** | 67 | — | → **0.134** | → 0.060 | **+0.074** |
| **webshop** | 170 | 0.382 | 0.382 → **0.400** | 0.382 → 0.371 | **+0.029** |
| **os** | 94 | — | 0.457 → **0.521** | 0.500 → 0.511 | **+0.010** |
| **autolab** | *仅 train（10 题）* | 0.30 | → **0.60** | → 0.50 | train **+0.10** |

> **结论**：4 个有 held-out 的 agentic 域里，**calib 冠军全部 ≥ nowmc 冠军**；GAIA 优势最大（+0.152，由 frame-audit 断路器贡献）。autolab 目前只有 train，calib 冠军 train 0.60 > nowmc 0.50。

---

## 二、各域详情

### GAIA（L1+L2，99 题 held-out）—— 优势最大

| 指标 | calib（frame-audit） | nowmc |
|------|---------------------|-------|
| Run | `gaia_..._calib_iter20_20260614_220212` | `gaia_..._nowmc_iter20_20260614_221605` |
| 同源 seed held-out | 0.293 | 0.283 |
| 冠军 | `iter016_conservative_quality_gated_summary` | `commit_and_recover`（@iter3）|
| **冠军 held-out** | **0.495**（L1 .500 / L2 .492） | 0.343（L1 .421 / L2 .295） |
| train 冠军分 | 0.575 | 0.425（iter3 后再未超越）|

- 同一 shared iter-0 seed 起跑、20 轮、唯一差异 = calib 多了 frame-audit（因果归因审计）断路器，是干净的 same-seed A/B。
- calib 0.495 同时击败：本轮 nowmc 0.343、改造前旧 calib 0.364、旧 nowmc 0.434。
- 收益集中在 **L2 多步任务**（.492 vs .295）。机制：frame-audit 识别出主导失败格是 native-tool-calling 端点层（而非搜索层），攻击下层后正确判定其为 model-limited，再把预算转给 summary 家族。

### tau2 banking_knowledge（67 题 held-out）

| 指标 | calib | nowmc |
|------|-------|-------|
| Run | `tau2_..._calib_iter20_20260613_170746` | `tau2_..._nowmc_iter20_20260613_150209` |
| 冠军 | `iter007_minimal_prompt_structured_action` | `iter010_mode_concentrated` |
| **冠军 held-out** | **0.134** | 0.060 |

- test 切片（task 31..97）约 95% 为 DB 型（64/67），DB 型从 train 0.30 降到 held-out ~0.05，存在切片分布偏移 + DB 内泛化下降。train 0.433/0.383 来自 30 题小 split。

### webshop（170 题 held-out）

| 指标 | calib | nowmc |
|------|-------|-------|
| Run | `webshop_..._calib_iter20_20260613_170746` | `webshop_..._nowmc_iter20_20260613_150209` |
| 冠军 | `iter002_tool_description_constraints` | `iter012_purchase_checkpoint` |
| seed pass@1 / mean | 0.382 / 0.614 | 0.382 / 0.634 |
| **冠军 pass@1** | **0.400** | 0.371 |
| 冠军 mean reward | 0.637 | 0.625 |

- nowmc 训练期 0.533 的高分在 held-out 回落到 0.371，低于自身 seed 0.382；calib 训练期保守的 0.467 → held-out 0.400，高于 seed。体现 calib 不追训练期高方差候选的特性。

### os（50-train / 94-test held-out）

| 指标 | calib | nowmc |
|------|-------|-------|
| Run | `os_..._calib_iter20_20260613_225547_os50tr` | `os_..._nowmc_iter20_20260613_225547_os50tr` |
| 冠军 | `iter005_os_bash_safety_tool_augment` | `iter010_os_stagnation_reflection` |
| seed held-out | 0.457 | 0.500 |
| **冠军 held-out** | **0.521** | 0.511 |
| 对自身 seed | +0.064 | +0.011 |

- 改用 50-train 后 calib 不再过拟合（旧 30-train 时 calib 冠军 0.535 < 自身 seed 0.561）。
- 两臂都收敛到 ~0.52 的能力天花板，calib 冠军 0.521 高于 nowmc 0.511。
- 更新的 calib run `..._20260615_183525_os50tr` 冠军 held-out 同为 **0.521**（复现一致）。
- ~11 个 persistent "completed-but-wrong" 任务两臂各试 15/17 轮、共 32 个候选都未攻破 → deepseek-v4-flash 真实能力墙，calib 的 model-limited 判定正确。

### autolab（**仅 train，10 题；held-out 待补**）

| 指标 | calib（frame-audit） | nowmc |
|------|---------------------|-------|
| Run | `autolab_..._calib_iter10_20260616_021343_frameaudit` | `autolab_..._nowmc_iter10_20260610_130209` |
| seed（terminus2_autolab） | 0.30 | 0.30 |
| **train 最佳 passrate** | **0.60**（`iter010_active_final_revalidation`）| 0.50（`iter009_empirical_metric_ratchet`）|
| train 最佳 score | 0.558（`iter005_broken_final_guard`）| 0.492（`iter008_terminal_correctness_barrier`）|

- 🚧 **目前只有 train 结果**，held-out 评估尚未完成（`runs/autolab_heldout_calib_fa/` 仅跑了 seed 一支）。
- proposer = claude-opus-4.8 native；calib 已按域移植 frame-audit 断路器（autolab 自毁特征 = 一簇任务 ~60s 内 0 分 = `terminus_2.py` 导入失败或 solver 401 stale key）。
- 另一支 frame-audit run `..._20260615_234810_frameaudit` 全 0（stale `OPENAI_API_KEY` 自毁），已弃用，不计入。

---

## 三、Proposer 开销

| 域 | calib run | 迭代 | proposer 调用 | 估算成本 | 耗时 |
|----|-----------|------|--------------|---------|------|
| GAIA | `..._calib_iter20_20260614_220212` | 20 | 20 | $50.36 | 3.1h |
| webshop | `..._calib_iter20_20260613_170746` | 20 | 20 | $49.01 | 2.4h |
| tau2 | `..._calib_iter20_20260613_170746` | 20 | 20 | $46.27 | 2.4h |
| os | `..._calib_iter20_20260613_225547_os50tr` | 20 | 20 | $44.57 | 2.4h |
| autolab | `..._calib_iter10_20260616_021343_frameaudit` | 10 | 10 | $36.67 | 1.9h |

---

## 四、口径说明

- **held-out 指标口径**：os/tau2/GAIA 为 pass@1（=mean，二值任务）；webshop 既报 pass@1（success 率）也报 mean episode reward（部分给分）。
- **冠军选取**：取各 run `best_candidates.json` / test_frontier 的 frontier 冠军，在冻结 test split 上重评；seed = passthrough 同 split。
- **GAIA 的收益**来自 2026-06-15 新增的 frame-audit（因果归因）断路器。
