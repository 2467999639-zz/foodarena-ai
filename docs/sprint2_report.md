# Sprint 2 迭代进展与复盘报告

主题：后端闭环与可解释战报。仓库基线：`496eb9d82c`；复盘日期：2026-10-07。计划归类：Issue #8–#13，共 6 项。

## 相关提交中的代码增量

FastAPI 会话接口、SQLite 持久化、交替辩论、结构化裁决与基础 BDD/Mock 测试。

**代码与 PR 证据：**`4c17145b19` 加入 FastAPI、SQLite 和 API；`c61fbcfde9` 加入 US01–US03 BDD、22 条评测集与安全 Mock；`0aae25501e` 加入故障/韧性回归。

## DoD 对照

源代码具备创建会话、辩论和战报闭环；基础 BDD 文件存在。是否在原定 Sprint 时间盒内完成不可从仓库还原。

| DoD 检查 | 结论 |
| --- | --- |
| 可追溯代码/PR | 有，见上方提交与 PR；提交时间只能证明记录进入历史的时间，不能证明任务实际完成日。 |
| 测试与质量门禁 | 仓库有自动化测试及 CI 配置；远端历史绿色状态未逐次核验。 |
| 文档/运行说明 | 以对应阶段可见文件为准；本次补齐规约与复盘。 |
| 安全/数据边界 | Mock 默认离线；密钥不应提交；样例菜单不代表真实食堂。 |

## 燃尽情况

| 口径 | 数值 |
| --- | ---: |
| 标记为 S2 的计划 Issue | 6 |
| 截至 2026-09-11 集中关闭后剩余 | 0 |
| 可验证的逐日故事点/剩余工时 | 无记录 |

这个 `计划数 → 0` 仅是期末关闭快照，并非时间序列燃尽曲线；部分 Issue 的关闭晚于代码提交，不能据此计算速度或准时率。

## 从代码推导的技术约束与改进建议

**静态推导（无原始阻碍记录）：**模型输出可能不符合 JSON/字段约束；重复启动会产生竞争风险；战报需要与会话成功状态保持一致。

**代码已有机制或待评审建议：**以 Pydantic 验证外部输出，以 `PENDING` 条件更新防重复执行，先保存推荐再标记 `SUCCESS`。

## 下轮或后续待办

对未满足或证据不足的 DoD 项目，保留验收记录、补可重现的运行命令与链接。每个 PR 应关联具体 Issue、写明测试结果及实际负责人，避免“创建者=开发者”的误判。


## 证据口径与项目分工

本报告是对公开仓库的**事后复盘**，不是原始 Sprint 日志。Issue 标题中的 `[Sx]` 作为计划归类；GitHub 上 26 个 Issue 均由 `wujiade-2005` 创建，均无 Assignee，不能据此认定开发负责人。可见功能、测试、前端、后端和文档提交主要由 `Lnxy-0` 署名；`wujiade-2005` 留有初始提交和合并提交。PR [#27](https://github.com/wujiade-2005/foodarena-ai/pull/27)、[#29](https://github.com/wujiade-2005/foodarena-ai/pull/29) 由 `Lnxy-0` 发起并已合并；PR [#28](https://github.com/wujiade-2005/foodarena-ai/pull/28) 在查询时仍为 open。未见可靠证据把各任务分配给更多具体成员。

**燃尽口径**：Issue 均已关闭，但除 #1 于 9 月 1 日关闭外，其余 25 项集中在 9 月 11 日关闭。仓库未提供逐日剩余工作量或故事点；因此仅列“计划 Issue 数 → 2026-09-11 关闭后剩余数”，不能绘制真实逐日燃尽曲线，也不能把集中关闭时间当作各轮实际完成时间。

**本次分析采用的 DoD 对照项（非历史验收记录）**：代码进入仓库、与 Pydantic/API 契约一致、Mock 可离线测试、后端 `ruff`/`pytest` 和前端 `lint`/`typecheck`/`vitest`/`build` 通过、文档及安全边界同步更新。此处“有 CI 配置”不等于已核验每次远端运行绿色；各项按当前基线可见代码核对，不能推导各轮历史门禁已通过。

## 来源

- [Sprint 2 Issue 检索](https://github.com/wujiade-2005/foodarena-ai/issues?q=is%3Aissue+%5BS2%5D)
- [提交历史](https://github.com/wujiade-2005/foodarena-ai/commits/main/)
- [CI 配置](https://github.com/wujiade-2005/foodarena-ai/blob/496eb9d82c/.github/workflows/ci.yml)

独立核对入口：[当前服务源码](https://github.com/wujiade-2005/foodarena-ai/blob/496eb9d82c/src/foodarena_ai/service.py)、[接口源码](https://github.com/wujiade-2005/foodarena-ai/blob/496eb9d82c/src/foodarena_ai/main.py)。本报告与其他新增文档均为分析产物，不作为相互证明的依据。
