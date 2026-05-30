# WorldCalib

延续 [Optimizer1](../Optimizer1) 的 LOCOMO + LongMemEval 优化循环，在它**之上加一层
world-model calibration 协议**（见 2026-05-27 与 ChatGPT 的设计讨论：
predict-then-execute、append-only calibration、POMDP frame、单 env model）。
对 default Optimizer1 流程的唯一改动：

1. 每个 run 多一个 append-only 文件 `runs/<run_id>/world_model_calibration.md`
2. 每个 iter 多一个 `runs/<run_id>/proposer_calls/iter_NNN/workspace/prediction.md`

剩下的（analyze / hypothesize / patch / `pending_eval.json` / eval）和 Optimizer1
逐字一致。

## 范围

**保留 + 移植**（locomo 和 longmemeval 优化所需的全部 Optimizer1 机制）：
- 数据 / scaffold / eval：`locomo.py`、`longmemeval.py`、`evaluation.py`、`baseline.py`、`metrics.py`、`model.py`、`pareto.py`、`schemas.py`、`scaffolds/`、`utils/`
- 优化循环：`optimizer.py`、`locomo_optimizer.py`、`longmemeval_optimizer.py`、`claude_runner.py`、`proposer_prompt.py`、`run_store.py`、`dynamic.py`、`post_eval.py`、`optimization_cells.py`、`benchmark_workspaces.py`、`traces/`
- 改写过的 proposer skill：`prompts/skills/{locomo,longmemeval}/SKILL.md`（加了 Calibration protocol 段 + workflow 步骤 0 / 步骤 3）

**新增**：
- `optimize_cli.py` — 精简的 console entry，注册为 `worldcalib-optimize`。比 Optimizer1 的 `cli.py` 小 7×，去掉了 codex / swebench / terminus / graph_colouring 路径
- `--prev-calibration PATH` flag — 用前一个 run 的 calibration 文件做 bootstrap

**故意不带过来**（保持仓库聚焦）：
- swebench / terminus / graph_colouring 全套
- `codex_runner.py`（只支持 claude proposer）
- `run_store_mcp_server.py`（loop 不依赖；以后单独决定）
- `source_base.py`、`benchmark_tasks.py`、`upstream.py`、`scaffolds/bm25_scaffold.py`（不在 loop 关键路径）

## 启动

```bash
cd /data/home/yuhan/WorldCalib
set -a && source .env && set +a   # symlink 到 Optimizer1/.env

# longmemeval-s, 5 iter, deepseek-v4-flash target, claude proposer
worldcalib-optimize --longmemeval --iterations 5 --limit 100 \
  --out runs/wc_lme_smoke_$(date +%Y%m%d_%H%M) \
  --model deepseek-v4-flash --base-url https://api.deepseek.com \
  --api-key "$DEEPSEEK_API_KEY" \
  --longmemeval-judge-model deepseek-v4-flash \
  --longmemeval-judge-base-url https://api.deepseek.com \
  --longmemeval-judge-api-key "$DEEPSEEK_API_KEY"

# 续跑：把上一个 run 的 calibration 作为种子
worldcalib-optimize --longmemeval --iterations 10 \
  --out runs/wc_lme_followup_$(date +%Y%m%d_%H%M) \
  --prev-calibration runs/wc_lme_smoke_*/world_model_calibration.md \
  ...
```

## 安装

```bash
pip install -e .
```

唯一外部依赖是 `httpx`。

## 数据

LOCOMO 和 LongMemEval-s 的数据通过 symlink 指向 `/data/home/yuhan/Optimizer1/data/{locomo,longmemeval}/`。如果要跑 LongMemEval m 或 oracle，先 `python -c "from worldcalib.longmemeval import prepare_longmemeval; prepare_longmemeval(variant='m', allow_download=True)"`。

## 已经跑好的 baseline（从 Optimizer1 整目录搬过来的，省得重跑）

`runs/` 下放了两份 2026-05-26 的 deepseek-v4-flash baseline，配置与 Optimizer1 那次一致：

| 路径 | benchmark | split | target model | passrate | 备注 |
|---|---|---|---|---|---|
| `runs/baseline_locomo_target_deepseek_v4_flash_20260526/` | LOCOMO | train 80 | deepseek-v4-flash | 0.2875 | scaffold = memgpt_source top12 |
| `runs/baseline_longmemeval_s_target_deepseek_v4_flash_fixedjudge_20260526/` | LongMemEval-s | train 100 | deepseek-v4-flash | 0.16 | judge = deepseek-v4-flash（必须） |

每个目录里有：
- `run_summary.json` — 顶层配置 + 分数
- `candidate_results/memgpt_source_top12.json` — 每个例子的预测、token、得分
- `traces/spans/iter_000/memgpt_source_top12.jsonl` — **关键**，每行一条 task 的结构化 trace（retrieval / answer span 全在里面）
- `traces/index.db`、`traces/manifest.json`、`traces/diagnostic/` — trace 元数据 / 索引
- `evolution_summary.jsonl`、`pareto_frontier.json`、`best_candidates.json`、`runstore.db` — Optimizer1 的 optimizer bookkeeping，对 WorldCalib 没用但留着备份

`runs/` 在 `.gitignore` 里——如果以后要把某次 baseline 钉死作为对照，单独 `git add -f`。

## 包名

包名是 `worldcalib`，不是 `optimizer1`。Optimizer1 也在同一个 venv 里以 `optimizer1` 名字编辑安装；两者并存不冲突。

## 下一步（设计方向）

参考与 ChatGPT 的讨论（任务优化与反馈模型 / world model calibration），这个 repo 计划落地：
- 把每个 benchmark 跑成 POMDP 中的 observable feedback 采集器
- proposer 每次出 candidate 时**先下注**：预测可观测反馈（trace、score、failure movement）
- benchmark 跑完后用 mismatch 校准 `world_model_calibration.md`
- 不维护独立 reward model；utility 是手写函数，写在 `objective.md`

SKILL.md 当前是 Optimizer1 原始版本，**待按上述协议改写**；MCP server `worldcalib-traces` 的引用待替换或删除。
