# 消融实验：A 有没有比 C 预测得更准？（累积 calibration 到底有没有用）

**日期**：2026-06-02
**作者**：Yuhan Chen (Ch1nyzzz)
**代码与原始产物**：`scripts/calib_value_test/`，机器生成结果见 `scripts/calib_value_test/out/REPORT.md` 与 `out/scores.json`

---

## 0. 一句话结论

让同一个 kimi-k2.6 预测**同一个固定 candidate** 的结果，比较两种状态：
**A**（真实 WMC proposer：读了累积的 `world_model_calibration.md`、自己设计了 candidate）
对 **C**（零 WMC：calibration 是空的）。

- **在客观的 passrate 维度，A 没有比 C 准**（A−C = −2.25，甚至略输）。
- A 在定性维度有一点稳定优势（+4.62），但它**不随 calibration 变厚而增长**
  （Spearman ≈ 0），是"自己设计的方案自己更懂"这个**恒定**效应，不是 calibration 累积的功劳。

**累积的 `world_model_calibration.md` 并没有让 proposer 把下一轮结果预测得更准。**
主实验里 WMC 的端到端收益，更可能来自 **predict-then-execute 这个纪律本身**，
而不是这份文件作为知识库被复用。

---

## 1. 核心问题与动机

WMC 协议让 proposer 每轮把对 candidate 的预测写下来、跑完用 mismatch 校准世界模型，
calibration 文件 **append-only、越积越厚**。一个直接的疑问是：

> 这份越来越厚的 calibration，真的让 proposer 对结果预测得**更准**了吗？

要回答它，就把同一个 proposer 放进两种世界里，让它预测**同一个已经定好的 candidate** 会怎样：

- **A**：它在真实那一轮的状态——读过 `iter < N` 的全部 distill，且这个 candidate 是它**自己设计**的。
- **C**：把 calibration **清空**（只留任务说明 preamble，零 distill），其余完全一样，重新预测同一个 candidate。

如果 calibration 有用，**A 应该比 C 预测得更准**，而且 calibration 越厚、A 的优势越大。

---

## 2. 实验设计

| 臂 | 看到的 calibration | candidate | 说明 |
|---|---|---|---|
| **A** | `iter < N` 的全部 distill（真实累积） | 自己设计的 | 真实 WMC proposer 当轮状态 |
| **C** | **空**（仅 788 字符任务 preamble，零 distill） | 同一个固定 candidate | 零 WMC 基线 |

两臂用**同一个 kimi-k2.6 模型**、**同一个真实结果**、**同一套盲评 rubric** 打分，
唯一有意改变的变量是"看不看得到累积 calibration"。

### 评分（composite 0–100）

| 维度 | 分值 | 怎么算 |
|---|---:|---|
| passrate-Δ | 40 | **确定性**：预测的分数区间是否套中真实 passrate（覆盖 25 + 锐度 15） |
| failure-type movement | 25 | 盲评判官 vs `prev→actual` 的 failure-cluster delta |
| trace movement | 20 | 盲评 vs token delta + 原始 `candidate_results` |
| side-effects | 15 | 盲评：回归 / 风险判断是否命中 |

**只有 passrate 维度是确定性、不依赖判官、且与"谁设计的 candidate"无关的**——
它是判断"A 是否真的更准"最干净的维度。

---

## 3. 实现与复现

全部在 `scripts/calib_value_test/`：

- `common.py` — `build_empty_calibration()`（C 的零知识 calibration）、预测区间解析、failure-cluster 计算。
- `stage.py` — 把每个 iter 的真实 proposer workspace 复制成 scratch，换上空 calibration + 固定 candidate + 预测-only prompt。
- `rerun_b.py --condition C` — 忠实复刻原始 proposer 调用（kimi-k2.6 / docker），只把 calibration 换空。
- `score.py` — 确定性 passrate 分 + 盲评输入 + A vs C 聚合（含厚度分桶）。
- `plot_trend.py` — 画 A vs C 随 iter 的趋势图。

```bash
ITERS=1,2,3,4,5,6,8,9,10,11,12,13,14,15,16,17,18,19,20,24,25,27,28,29
python scripts/calib_value_test/stage.py     --iters $ITERS
python scripts/calib_value_test/rerun_b.py --condition C --iters $ITERS --workers 4
python scripts/calib_value_test/score.py     --iters $ITERS --emit-inputs
# 每个 out/iter_NNN/scorer_input_C.md 跑一个盲评 subagent → llm_score_C.json
#（A 的盲评分沿用原始批次）
python scripts/calib_value_test/score.py     --iters $ITERS --aggregate
python scripts/calib_value_test/plot_trend.py
```

覆盖 LongMemEval-s WMC run 的 **24 个 iter**（A、C 各 24 条预测）。

---

## 4. 结果

### 4.1 配对统计（Δ = A − C，**正数 = A 预测得更准**）

| 维度 | mean Δ | t | A 胜/负/平 |
|---|---:|---:|:--:|
| **passrate（客观）** | **−2.25** | −1.27 | **4 / 12 / 8** |
| 定性（fail+trace+side） | +4.62 | +3.26 | 18 / 5 / 1 |
| composite | +2.38 | +0.93 | 13 / 10 / 1 |

均值 composite：**A = 45.0，C = 42.7**（/100）。

读法：
- **客观 passrate 维度，A 反而略输 C**（−2.25，12 负 4 胜）——看了 calibration 并没有让数值预测更准。
- A 的 composite 略高，**全部来自定性维度**（+4.62，显著）。

### 4.2 逐 iter（A vs C 的 composite）

| iter | actual | A pass | A tot | C pass | C tot | A−C |
|---|---|---|---|---|---|---|
| 1 | 0.38 | 15.0 | 45.0 | 28.8 | 52.8 | −7.8 |
| 2 | 0.47 | 34.0 | 76.0 | 17.5 | 42.5 | +33.5 |
| 3 | 0.27 | 0.0 | 20.0 | 0.0 | 22.0 | −2.0 |
| 4 | 0.49 | 5.0 | 28.0 | 20.0 | 48.0 | −20.0 |
| 5 | 0.39 | 0.0 | 14.0 | 0.0 | 8.0 | +6.0 |
| 6 | 0.50 | 12.5 | 51.5 | 34.8 | 64.8 | −13.2 |
| 8 | 0.53 | 20.0 | 45.0 | 12.5 | 34.5 | +10.5 |
| 9 | 0.54 | 17.5 | 52.5 | 15.0 | 34.0 | +18.5 |
| 10 | 0.53 | 12.5 | 47.5 | 20.0 | 49.0 | −1.5 |
| 11 | 0.47 | 2.5 | 29.5 | 7.5 | 31.5 | −2.0 |
| 12 | 0.57 | 34.8 | 72.8 | 17.5 | 53.5 | +19.2 |
| 13 | 0.63 | 35.5 | 86.5 | 35.5 | 71.5 | +15.0 |
| 14 | 0.66 | 37.0 | 75.0 | 37.8 | 74.8 | +0.2 |
| 15 | 0.66 | 17.5 | 37.5 | 22.5 | 48.5 | −11.0 |
| 16 | 0.69 | 37.0 | 77.0 | 37.8 | 73.8 | +3.2 |
| 17 | 0.17 | 0.0 | 4.0 | 0.0 | 4.0 | +0.0 |
| 18 | 0.64 | 7.5 | 33.5 | 12.5 | 46.5 | −13.0 |
| 19 | 0.61 | 2.5 | 35.5 | 5.0 | 24.0 | +11.5 |
| 20 | 0.69 | 22.5 | 52.5 | 37.8 | 68.8 | −16.2 |
| 24 | 0.62 | 2.5 | 24.5 | 7.5 | 28.5 | −4.0 |
| 25 | 0.69 | 22.5 | 62.5 | 22.5 | 45.5 | +17.0 |
| 27 | 0.71 | 37.8 | 70.8 | 37.8 | 65.8 | +5.0 |
| 28 | 0.68 | 15.0 | 33.0 | 15.0 | 29.0 | +4.0 |
| 29 | 0.11 | 0.0 | 7.0 | 0.0 | 3.0 | +4.0 |

### 4.3 A 的优势随 iter 怎么变？

calibration 每轮变厚，C 永远空白。**若累积内容有用，A−C 应随 iter 增长。** 实测相反：

![A vs C 随 iter 趋势](scripts/calib_value_test/out/trend_A_vs_C.png)

| A − C | 前 12 iter 均值 | 后 12 iter 均值 | 线性斜率 |
|---|---:|---:|---:|
| 定性 gap | +6.33 | +2.92 | −0.08 / iter |
| 总分 gap | +4.69 | +0.06 | −0.05 / iter |

A 的优势**递减、不递增**——后半几乎归零。

### 4.4 直接按 calibration 厚度分桶（核心检验）

把 24 个 iter 按 A 当时真实看到的 calibration **字符数**三等分：

| 厚度桶 | n | 字符范围 | A−C composite | **A−C passrate** | A−C 定性 |
|---|---|---|---:|---:|---:|
| 薄 | 8 | 787–9281 | +3.2 | **−3.1** | +6.2 |
| 中 | 8 | 10566–21809 | +2.9 | **−0.2** | +3.1 |
| 厚 | 8 | 23467–31387 | +1.0 | **−3.5** | +4.5 |

- **Spearman(厚度, A−C composite gap) = +0.06**（无相关）
- **Spearman(厚度, A 的绝对 composite) = −0.05**（厚 calibration 没让 A 更准）

calibration 从 787 字符堆到 3 万字符，A 相对 C 的优势**完全没有变大**；
客观 passrate 维度上 A 在**三个桶里全是负的**——无论 calibration 多厚，A 都没比 C 准。

---

## 5. 结论

**A 有没有比 C 预测得更准？**

- **客观 passrate 维度：没有**（A−C = −2.25，A 甚至略输；厚薄三个桶全负）。读累积 calibration **没有**让 proposer 的数值预测变准。
- **定性维度：A 有一点稳定优势**（+4.62，显著）——但这个优势**不随 calibration 变厚而增长**（Spearman ≈ 0、随 iter 斜率为负）。这正是一个**恒定**效应的指纹：A 是 candidate 的**设计者**、天然更懂自己改动的 failure mode，与 calibration 攒了多厚无关。

一个稳健性论据让这个判断更硬：定性维度是盲评，A、C 的分来自不同判官批次，**系统性批次偏差只会整体平移曲线、不会制造"随厚度/iter 下降"的斜率**——而正是这个"平 / 降"的趋势承担了主结论，所以它不受批次抖动影响。

> **累积的 `world_model_calibration.md` 不会让 proposer 把 iteration 结果预测得更准。**
> 端到端 WMC proposer 整体只是微弱领先，且这点领先在 calibration 厚度上是平的、
> 在唯一与"谁设计 candidate"无关的客观维度上是缺失的。这与主实验中 WMC 的收益来自
> **predict-then-execute 的纪律本身**（强制下注 + 对齐 mismatch）、而非把 calibration
> 当知识库越攒越值钱，是一致的。

---

## 6. Caveats

1. **同一个模型、同一个固定 candidate**，有意改变的变量是"calibration 空 vs 累积"。A 额外**自己设计了 candidate**，这在定性维度对 A 有利——也正是 A 定性占优的来源。
2. **passrate 维度是确定性的**；定性维度是盲评，A 与 C 的子分来自不同判官批次，可能有一个恒定的批次偏移——但它无法制造"随厚度/iter 下降"的趋势，而趋势才是承重结论。
3. **样本量**：n = 24，单 run（LongMemEval-s），单 proposer（kimi-k2.6）。

---

*相关：主实验报告见 [`REPORT.md`](REPORT.md)（control vs WMC 端到端）；本消融针对其中的 LongMemEval-s WMC run。*
