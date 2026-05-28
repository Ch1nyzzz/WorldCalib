# WorldCalib: World-Model Calibration 实验报告

**日期**：2026-05-28
**作者**：Yuhan Chen (Ch1nyzzz)

---

## 摘要

我们在 **LongMemEval-s** 和 **LOCOMO** 上，给 proposer 加了一层 **World-Model
Calibration（WMC）协议**——让 proposer 在每轮提出 candidate 之前**先下注**，
跑完之后用 mismatch **append-only 校准**自己的世界模型。两个任务上都决定性
超过对应的对照实验：

| Benchmark | 对照 best | WMC best | Δ 绝对 | Δ 相对 |
|---|---:|---:|---:|---:|
| **LongMemEval-s** | 0.59 @ iter_30 | **0.71** @ iter_27 | **+0.12** | **+20.3%** |
| **LOCOMO** | 0.412 @ iter_08 | **0.475** @ iter_17 | **+0.063** | **+15.3%** |

同时 proposer 总成本下降 22-25%（LME $103→$77；LOCOMO $121→$94）。

---

## 1. 怎么跑的

| 组件 | 配置 |
|---|---|
| Proposer | Claude Kimi K2.6 max effort（docker-claude-kimi 调 `api.kimi.com/coding`） |
| Target | DeepSeek v4 Flash (`api.deepseek.com`) |
| LME judge | DeepSeek v4 Flash |
| Scaffold seed | `memgpt_source top12`（LME 100 题 train；LOCOMO 80 题 train） |
| Selection policy | `default` |
| 迭代 | 30 iter，每 iter eval workers = 64 |

启动一条命令：

```bash
cd /data/home/yuhan/WorldCalib && set -a && source .env && set +a
bash scripts/launch_wmc_default_nosummary.sh   # locomo + longmemeval 并行
```

每个 run 跑约 10 小时，落到 `runs/<run_id>/`。

---

## 2. World-Model Calibration 怎么设计

WMC 在标准 proposer 循环上**只多两个文件、一个协议**：

| 文件 | 写谁 | 时机 | 内容 |
|---|---|---|---|
| `world_model_calibration.md`（run-level，append-only） | proposer | 每 iter 开头 | 读上一轮 prediction 和真实 trace，append `## iter_NNN distill`：mismatch 在哪、根因是什么 |
| `prediction.md`（per-iter） | proposer | 提出 candidate 时 | **下注**：当前 candidate 对每类 question type / failure mode 的预测 passrate，以及为什么 |

**机制**：proposer 必须 **predict-then-execute**——提 candidate 必须同时
写下"我赌它在 X 类题目上得 0.5、Y 类得 0.3"；下一轮先把这个预测和实际
结果对齐成一段 distill，再做新决策。

**设计原则**：
- **Append-only**：写错了不能删，下一轮必须用 mismatch 来 distill
- **简单**：不引入独立 reward model、shadow gate、第二个 LLM judge
- **Docker-safe**：calibration 文件 copy-in / copy-out 进 workspace，proposer 用 cwd-local 路径访问
- **可观测对齐**：禁止写不可证伪的 generalization judgement，只允许 outcome predictions 和 concrete mismatch

**实现**：
- `src/worldcalib/optimizer.py` 的 `_sync_calibration_into_workspace` / `_sync_calibration_back_from_workspace` 负责文件 in/out
- `src/worldcalib/prompts/skills/{locomo,longmemeval}/SKILL.md` 的 `## Calibration protocol` 段告诉 proposer 协议
- `src/worldcalib/optimize_cli.py` 的 `--prev-calibration PATH` flag 支持用前一个 run 的 calibration 做 bootstrap

---

## 3. 实验结果

### 3.1 优化效果

baseline（iter_0，未优化）：LME 0.16；LOCOMO 0.287。

| Benchmark | 对照 best | WMC best | baseline→best gain |
|---|---:|---:|---|
| LongMemEval-s | 0.590 | **0.710** | 对照 +0.43 → WMC **+0.55** |
| LOCOMO | 0.412 | **0.475** | 对照 +0.125 → WMC **+0.188** |

末轮稳定性（iter_27-30 平均）：LME 0.473 → **0.548**；LOCOMO 0.350 → **0.420**。

### 3.2 突破速率 (speed-to-threshold)

**LongMemEval-s**：

| 阈值 | 对照首次到达 | WMC 首次到达 | 加速 |
|---:|---:|---:|---:|
| 0.30 | iter_05 | iter_01 | 5× |
| 0.49 | iter_15 | iter_04 | 3.75× |
| 0.55 | iter_23 | iter_12 | 1.92× |
| 0.60 | — | iter_13 | inf |
| 0.70 | — | iter_27 | inf |

**LOCOMO**：

| 阈值 | 对照首次到达 | WMC 首次到达 | 加速 |
|---:|---:|---:|---:|
| 0.40 | iter_08 | iter_06 | 1.33× |
| 0.412 | iter_08 | iter_07 | 1.14× |
| 0.45 | — | iter_10 | inf |
| 0.475 | — | iter_17 | inf |

对照在 LOCOMO 上反复撞 0.412 天花板（iter 8 / 13 / 16 / 21 / 23 五次）；
WMC 在 iter_10 一次突破到 0.45，继续推到 0.475。

### 3.3 成本

| Benchmark | Run | Proposer cost | Duration | Cache hit |
|---|---|---:|---:|---:|
| LME-s | 对照 | $102.81 | 9h01m | 41.8% |
| LME-s | **WMC** | **$77.08** | 9h52m | **42.7%** |
| LOCOMO | 对照 | $120.81 | 10h25m | 41.7% |
| LOCOMO | **WMC** | **$93.88** | 9h41m | **43.8%** |

calibration 是 append-only 累积上下文（每 iter 几百 token，到 iter_27 累积约 5KB），
作为稳定 prefix 让 cache 命中率上升；proposer 因为有一份现成的全局 distill，
Read calls 下降 28-40%（LME 731→436，LOCOMO 756→542），整体更便宜。

### 3.4 Scaffold 演化亮点

- **LME**：对照在 iter_30 才达到 0.59（`answer_type_aware_retrieval`）；WMC 在 iter_20 就到 0.69（`multi_objective_compression_with_answer_type_scoring`），思路一致但**早 10 iter** 找到，再继续推进到 iter_27 的 `mmr_diversity_rerank_2048` = 0.71
- **LOCOMO**：对照困在 truncation 防御 / temporal grounding 路线反复撞 0.412；WMC 在 iter_17 切到 **context expansion + compression** 组合一次突破 0.45

---

## 4. 局限与下一步

- **单 run 比较**：每组只跑了 1 次，下一步做 3 seed 复现报告 mean±std
- **WMC test-frontier 未集成**：对照跑了 held-out test eval（LME top-1 test 0.5325；LOCOMO top-1 test 0.3692），WMC 留作下一步
- **calibration 误诊**：定性观察到一次（proposer distill 写错根因）；已加 3 条 SKILL.md hard rules 缓解，但需要 calibration audit pipeline 量化
- **其他 selection policy**：试 progressive / bandit，看 WMC 是否仍 dominate
- **更难的 benchmark**：上 SWE-bench mini，验证 calibration 在 code-fix 任务上是否仍 transfer

---

## 5. 复现 & 数据

复现命令：见 §1。

引用数据：
- 每 iter 每 candidate passrate：`runs/<run_id>/candidate_score_table.json`
- 最佳 candidate 详情：`runs/<run_id>/best_candidates.json`
- 总 token / cost / duration：`logs/<run_id>.log` 末尾的 run_summary JSON
- 完整 distill 历史：`runs/<run_id>/world_model_calibration.md`

本报告所有数字的 mechanical extraction 源 CSV：`data/trajectories/{lme,loc}_{nowmc,wmc}.csv`。

---

*报告生成于 2026-05-28，基于 2026-05-26 / 27 / 28 三次完整 30-iter run。*
