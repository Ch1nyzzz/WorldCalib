# WorldCalib: World-Model Calibration 实验报告

**日期**：2026-05-28
**作者**：Yuhan Chen (Ch1nyzzz)

---

## 摘要

我们在 **LongMemEval-s** 和 **LOCOMO** 上，给 proposer 加了一层 **World-Model
Calibration（WMC）协议**——让 proposer 在每轮提出 candidate 之前**先下注**，
跑完之后用 mismatch **append-only 校准**自己的世界模型。两个任务上都决定性
超过对应的对照实验：

**Train passrate**：

| Benchmark | 对照 best | WMC best | Δ 绝对 | Δ 相对 |
|---|---:|---:|---:|---:|
| **LongMemEval-s** | 0.59 @ iter_30 | **0.71** @ iter_27 | **+0.12** | **+20.3%** |
| **LOCOMO** | 0.412 @ iter_08 | **0.475** @ iter_17 | **+0.063** | **+15.3%** |

**Held-out test passrate**：

| Benchmark | 对照 top-1 | WMC top-1 | Δ 绝对 | Δ 相对 |
|---|---:|---:|---:|---:|
| **LongMemEval-s** (400 题) | 0.5325 | **0.6075** | **+0.075** | **+14.1%** |
| **LOCOMO** (1449 题) | 0.3692 | **0.4534** | **+0.084** | **+22.7%** |

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

### 3.1 优化效果 (train)

baseline（iter_0，未优化）：LME 0.16；LOCOMO 0.287。

| Benchmark | 对照 best | WMC best | baseline→best gain |
|---|---:|---:|---|
| LongMemEval-s | 0.590 | **0.710** | 对照 +0.43 → WMC **+0.55** |
| LOCOMO | 0.412 | **0.475** | 对照 +0.125 → WMC **+0.188** |

末轮稳定性（iter_27-30 平均）：LME 0.473 → **0.548**；LOCOMO 0.350 → **0.420**。

### 3.2 泛化（held-out test）

各自取 train 上的 quality frontier top-3 candidate 在 test 集上重新评估：

| Benchmark | Test 题数 | 对照 top-1 test | WMC top-1 test | Δ |
|---|---:|---:|---:|---:|
| LongMemEval-s | 400 | 0.5325 (`adaptive_recovery_temporal_facet`) | **0.6075** (`adjacent_archival_merge_1536`) | **+0.075 (+14.1%)** |
| LOCOMO | 1449 | 0.3692 (`temporal_aligned_retrieval`) | **0.4534** (`context_expansion_with_compression`) | **+0.084 (+22.7%)** |

LOCOMO 的 test 相对 gain (+22.7%) 比 train (+15.3%) 还高——WMC 找到的 scaffold 不只是 train 上更好，泛化能力也更强。

### 3.3 突破速率 (speed-to-threshold)

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

### 3.4 成本

| Benchmark | Run | Proposer cost | Duration | Cache hit |
|---|---|---:|---:|---:|
| LME-s | 对照 | $102.81 | 9h01m | 41.8% |
| LME-s | **WMC** | **$77.08** | 9h52m | **42.7%** |
| LOCOMO | 对照 | $120.81 | 10h25m | 41.7% |
| LOCOMO | **WMC** | **$93.88** | 9h41m | **43.8%** |

calibration 是 append-only 累积上下文（每 iter 几百 token，到 iter_27 累积约 5KB），
作为稳定 prefix 让 cache 命中率上升；proposer 因为有一份现成的全局 distill，
Read calls 下降 28-40%（LME 731→436，LOCOMO 756→542），整体更便宜。

### 3.5 Scaffold 演化亮点

- **LME**：对照在 iter_30 才达到 0.59（`answer_type_aware_retrieval`）；WMC 在 iter_20 就到 0.69（`multi_objective_compression_with_answer_type_scoring`），思路一致但**早 10 iter** 找到，再继续推进到 iter_27 的 `mmr_diversity_rerank_2048` = 0.71
- **LOCOMO**：对照困在 truncation 防御 / temporal grounding 路线反复撞 0.412；WMC 在 iter_17 切到 **context expansion + compression** 组合一次突破 0.45

---

## 4. 后验校准检验：世界模型本身让预测更准吗？（2026-06-03）

§3 证明的是 **WMC 端到端更好**（找到更好的 scaffold）。但"找到更好的 patch"不等于
"对结果预测得更准"。要单独验证后者，必须把"有没有世界模型"做成唯一变量，离线、去除在线选择偏置地比一次。

### 4.1 方法：无偏成对盲判（`scripts/posthoc_calib_predict.py`）

对一个已完成 run 的固定候选，起**两个全新预测器**（都不曾设计该候选）去预测同一个候选、用同一逐题型两面协议，**唯一差别**是有没有读世界模型：

- `no-WM`：不给世界模型；
- `WMC-WM` / `calib-WM`：给该 run 最终的 `world_model_calibration.md`，但**删掉该候选自己那段
  distill**（leave-one-out，杜绝开卷查到自己的真实结果）。

打分**不用绝对分**：把两份预测**匿名成 A/B（按候选随机，抵消位置偏置）**，连同**客观真实结果**
（代码机械算出的逐题型实际涨跌）一起交给**同一个裁判**（kimi-k2.6 全新 context，与 proposer 同套唤起），
只判哪份更准。这套设计同时去掉了三种偏置：**designer 偏置**（两臂都不设计候选）、**跨批次刻度偏置**
（同一裁判头对头）、**开卷泄漏**（leave-one-out）。每个 run 随机抽 10 个候选。

### 4.2 结果（每格 no-WM → 有-WM）

| run | WM 盲判胜率 | upside_hit | downside_recall |
|---|---|---|---|
| **WMC LME** | **10 / 10** | 0.905 → 0.915 | **0.0 → 1.0** |
| **WMC LoCoMo** | **9 / 10** | 0.30 → 0.50 | —（本批无量级回归） |
| **calib LME** | **8 / 10** | 0.41 → 0.49 | 0.29 → 0.50 |
| **calib LoCoMo** | **9 / 10** | 0.15 → 0.25 | 0.57 → 0.71 |
| **合计** | **36 / 40 = 90%** | 一致 ↑ | 一致 ↑ |

**读法**：整体方向/量级两臂差别不大（upside_hit 接近），**WM 的优势几乎全在"预判回归"**——
没有 WM 的预测器天真乐观、几乎不预判回归（LME recall 0.0），读过累积世界模型的它能点名哪些题型会退化
（LME recall 1.0）。四组在 run 内部一致显示**有 WM 比没 WM 准**。

### 4.3 含义

- **世界模型作为知识库确有信息量**：它让一个对候选毫无先验的全新预测器预测得更准，价值集中在逐题型、
  尤其是回归识别这一维。
- 这**修订**了早先一版只测"标量 passrate 区间命中"、且混入 designer / 跨批次偏置的消融结论
  （详见 [`ABLATION_calibration_value.md`](ABLATION_calibration_value.md)）——原方法恰好没测到 WM 真正起作用的那一维。
- **边界**：本检验用统一逐题型协议，衡量的是 **WM 作为知识件的信息量**（有它 vs 没它），不等同于各变体
  当年实际所写预测本身的准度；run 内对照干净，跨 run 胜率高低不宜直接比较（候选/抽样不同）；n=10。

---

*§0–§3 报告生成于 2026-05-28，基于 2026-05-26 / 27 / 28 三次完整 30-iter run；*
*§4 后验校准检验补充于 2026-06-03（产物在 `runs/_posthoc_calib/`）。*
