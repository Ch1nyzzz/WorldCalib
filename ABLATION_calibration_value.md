# 消融实验：累积的世界模型（WMC）有没有让预测更准？

**日期**：2026-06-03
**作者**：Yuhan Chen (Ch1nyzzz)
**代码**：`scripts/posthoc_calib_predict.py`　**产物**：`runs/_posthoc_calib/<run>/{results.jsonl,summary.json}`

---

## 0. 一句话结论

把同一个固定 candidate 交给两个**全新**的 kimi-k2.6 预测器去预测，唯一差别是有没有读 WMC
累积的 `world_model_calibration.md`：

- **`no-WM`**：不给世界模型。
- **`WMC-WM`**：给该 run 最终的 `world_model_calibration.md`，但**删掉这个候选自己那段
  distill**（leave-one-out，杜绝开卷）。

同一个裁判同时看到两份**匿名**预测 + 客观真实结果，只判哪份更准。结果：

> **有 WMC 世界模型的预测器明显更准 —— WMC LME 10/10、WMC LoCoMo 9/10，
> 优势几乎全集中在"预判回归"上（LME 的 downside recall 从 0.0 升到 1.0）。**

也就是说，**这份越积越厚的 `world_model_calibration.md` 作为知识库确有信息量**：它让一个对候选
毫无先验、谁都没设计过它的全新预测器，预测得更准。

---

## 1. 核心问题

WMC 协议让 proposer 每轮写下对 candidate 的预测、跑完用 mismatch 校准世界模型，
`world_model_calibration.md` **append-only、越积越厚**。直接的疑问是：

> 这份越来越厚的 calibration，真的携带了能让"预测更准"的知识吗？

要干净地回答它，就必须把"有没有这份文件"做成**唯一变量**，其余全部对齐，再让一个独立裁判判准度。

---

## 2. 实验设计：无偏的成对盲判（pairwise blind judge）

| | `no-WM` 臂 | `WMC-WM` 臂 |
|---|---|---|
| 世界模型 | 空 | 最终 `world_model_calibration.md`，**删掉该候选自己的 distill 段** |
| candidate | 同一个固定候选 | 同一个固定候选 |
| 是谁设计的 | **都不是预测器设计的**（两臂都是 fresh predictor） | 同左 |
| 预测协议 | 逐题型两面（Upside/Downside + Net bet） | 同左 |
| 模型/唤起 | kimi-k2.6 / docker，与 proposer 同一套 | 同左 |

每个候选两臂喂**完全相同**的 parent 源码 + diff + base 通过率表，**唯一有意改变的变量就是有没有
那份 WMC 世界模型**。

**为什么这样设计能去掉偏置**

1. **两臂都不设计 candidate** → 去掉"设计者天然更懂自己改动"的 designer 偏置。
2. **同一个裁判头对头盲判** → 不再用两套独立批次的绝对分相减，去掉跨批次的恒定刻度偏移。
3. **leave-one-out 删掉该候选自己的 distill** → WMC-WM 不能开卷查到这个候选的真实结果，靠的是
   其余轮次沉淀下来的泛化。

### 客观真实结果 + 裁判

- **ground truth（代码机械算，不靠裁判主观）**：candidate 相对 base 的**逐题型** passrate 实际涨跌
  （哪些类涨了、哪些类跌了、整体 Δ），由 `prediction_feedback` 计算。
- **裁判**：再起一个 kimi-k2.6 全新独立 context，读到「客观结果 + 两份匿名预测（A/B 顺序按候选随机，
  抵消位置偏置）」，只回答 `WINNER: A|B|TIE` + 理由。**判的是哪份预测与客观结果更吻合**
  （说中了真正动的题型、抓到真实回归、整体方向对），不判文笔、不判 patch 好坏。
- 解匿名后统计 `WMC-WM` 对 `no-WM` 的胜率，并顺带记录两臂的机械指标做交叉验证。

---

## 3. 结果（每个 run 随机抽 10 个候选；每格 no-WM → WMC-WM）

| run | WM 盲判胜率 | upside_hit | downside_recall | surprise 回归(↓更好) |
|---|---|---|---|---|
| **WMC LME** | **10 / 10** | 0.905 → 0.915 | **0.0 → 1.0** | 0.1 → 0.0 |
| **WMC LoCoMo** | **9 / 10** | 0.30 → 0.50 | —（本批无量级回归） | 0.0 → 0.0 |

**怎么读**

- **整体方向/量级两臂基本持平**（upside_hit 0.905 ≈ 0.915）——预测整体涨多少这件事，有没有 WM 差别不大。
- **WM 的优势全在回归识别**：LME 上 `no-WM` 一个真实回归都没抓到（recall 0.0，天真乐观），
  `WMC-WM` 全抓到了（1.0）；裁判 10/10 选了 WMC-WM。LoCoMo 这批候选相对 clean 基本只涨没有
  量级回归，所以 downside recall 两臂都无定义，WM 的优势体现在 upside（0.30→0.50）与裁判综合判断（9/10）。
- **位置偏置已排除**：WM 臂在不同候选里随机被放成 Prediction A 或 B，裁判不论它在哪个位置都选了它。
- **ground truth 可靠**：LME 重算的逐类 Δ 与在线记录一致；LoCoMo 用 per-task 记录重算的逐类通过率，
  其加权整体值与原始 `all` 桶**精确相等**（无失败）。

---

## 4. 结论

**在去掉 designer 偏置、跨批次刻度偏置，并用逐题型/回归维度作客观标尺的无偏头对头下，
WMC 累积的世界模型确实让一个全新预测器预测得更准（WMC LME 10/10、WMC LoCoMo 9/10），
优势集中在"预判回归"。** 这份 `world_model_calibration.md` 作为知识库**确有**可复用的信息量。

它真正起作用的维度是**逐题型、尤其是回归识别**——一个没有任何先验的预测器天然乐观、不会预判
回归，而读过 WMC 沉淀的它能点名哪些题型会退化。

---

## 5. Caveats

1. **统一预测协议**：两臂都用逐题型两面协议预测。本实验衡量的是 **WMC 世界模型作为知识件的信息量**
   （有它 vs 没它），不等同于"WMC 当年实际写的那种整体标量 + 失败簇预测本身的准度"——后者是另一个问题。
2. **干净成立的是 run 内部的 no-WM vs WMC-WM 对照**；两个 run 之间的胜率高低不宜直接比较
   （候选不同、抽样 iter 不同）。
3. **样本量**：每个 run 随机抽 10 个候选（seed=13），单 proposer（kimi-k2.6）。LoCoMo 这批没有量级回归，
   回归识别维度无法在该 run 上体现。

---

## 6. 复现

```bash
# WMC LongMemEval-s（抽到 iters 2,5,6,9,10,11,20,24,25,27）
python3 scripts/posthoc_calib_predict.py \
  --run-dir runs/longmemeval_s_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260527_212607 \
  --sample 10 --concurrency 4

# WMC LoCoMo（旧 run 仅有 all 桶，用 --recompute-locomo-categories 从 per-task 记录重算逐类）
python3 scripts/posthoc_calib_predict.py \
  --run-dir runs/locomo_claudekimi_k26_maxeffort_target_deepseek_v4_flash_default_nosummary_wmc_iter30_20260528_001003 \
  --sample 10 --concurrency 4 --recompute-locomo-categories
```

每个候选产生 `no_wm/`、`calib_wm/`（即 WMC-WM 臂）两份预测与一个 `judge/` 裁决；
逐候选明细见 `results.jsonl`，汇总见 `summary.json`。

---

*相关：主实验报告见 [`REPORT.md`](REPORT.md)（control vs WMC 端到端）。*
