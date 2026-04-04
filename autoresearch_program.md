# Nini Autoresearch Program（兼容入口）

根目录方法论文档已拆分为双线管理：

- 第一条 `static`：见 [docs/autoresearch/static/PROGRAM.md](/home/lewis/coding/scientific_nini/docs/autoresearch/static/PROGRAM.md)
- 第二条 `harness`：见 [docs/autoresearch/harness/PROTOCOL.md](/home/lewis/coding/scientific_nini/docs/autoresearch/harness/PROTOCOL.md)
- 总索引与边界规则：见 [docs/autoresearch/README.md](/home/lewis/coding/scientific_nini/docs/autoresearch/README.md)

迁移后的强规则：

1. `static` 和 `harness` 不共享 baseline。
2. `static` 和 `harness` 不共享 results 账本。
3. 单次实验只能属于一条线。
4. `keep/discard` 只能由本线 evaluator 决定。

兼容说明：

- 旧脚本 `scripts/run_experiment.sh` 仍可用，但现在转发到 `scripts/run_static_experiment.sh`
- 旧脚本 `scripts/measure_baseline.py` 仍可用，但只服务 `static` 线
