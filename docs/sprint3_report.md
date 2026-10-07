# Sprint 3 迭代进展与复盘报告

主题：前端实时交互与韧性。仓库基线：`496eb9d82c`；复盘日期：2026-10-07。计划归类：Issue #14–#20，共 7 项。

## 相关提交中的代码增量

React/Vite 偏好表单、辩论和战报页面，SSE 实时消息/重连；输入与 Prompt 注入防护、日志脱敏、22 条 Mock 评测集。

**代码与 PR 证据：**`9b2561e00d` 加入前端；`acb1be7ebf` 和 `4d91493dde` 修复实时事件与轮流展示；`e57eab9679` 修复第三方日志格式安全。

## DoD 对照

页面和流式实现可见，测试文件可见；真实 SSE 逐条到达应以本地运行复核。当前失败页“重试”只刷新并重放 `FAILED`，未满足用户预期的原地重试。

| DoD 检查 | 结论 |
| --- | --- |
| 可追溯代码/PR | 有，见上方提交与 PR；提交时间只能证明记录进入历史的时间，不能证明任务实际完成日。 |
| 测试与质量门禁 | 仓库有自动化测试及 CI 配置；远端历史绿色状态未逐次核验。 |
| 文档/运行说明 | 以对应阶段可见文件为准；本次补齐规约与复盘。 |
| 安全/数据边界 | Mock 默认离线；密钥不应提交；样例菜单不代表真实食堂。 |

## 燃尽情况

| 口径 | 数值 |
| --- | ---: |
| 标记为 S3 的计划 Issue | 7 |
| 截至 2026-09-11 集中关闭后剩余 | 0 |
| 可验证的逐日故事点/剩余工时 | 无记录 |

这个 `计划数 → 0` 仅是期末关闭快照，并非时间序列燃尽曲线；部分 Issue 的关闭晚于代码提交，不能据此计算速度或准时率。

## 从代码推导的技术约束与改进建议

**静态推导（无原始阻碍记录）：**实时流相关修复提交说明该处曾有实现调整；未提供当时复现日志。由同步调用与事件迭代方式可推导缓冲风险，不能证明每个用户都曾遇到此现象。

**代码已有机制或待评审建议：**在 Starlette 工作线程推进生成器；增加分步流式回归，并将失败页按钮改为创建新会话或补真正重试 API。

## 下轮或后续待办

对未满足或证据不足的 DoD 项目，保留验收记录、补可重现的运行命令与链接。每个 PR 应关联具体 Issue、写明测试结果及实际负责人，避免“创建者=开发者”的误判。


## 证据口径与项目分工

本报告是对公开仓库的**事后复盘**，不是原始 Sprint 日志。Issue 标题中的 `[Sx]` 作为计划归类；GitHub 上 26 个 Issue 均由 `wujiade-2005` 创建，均无 Assignee，不能据此认定开发负责人。可见功能、测试、前端、后端和文档提交主要由 `Lnxy-0` 署名；`wujiade-2005` 留有初始提交和合并提交。PR [#27](https://github.com/wujiade-2005/foodarena-ai/pull/27)、[#29](https://github.com/wujiade-2005/foodarena-ai/pull/29) 由 `Lnxy-0` 发起并已合并；PR [#28](https://github.com/wujiade-2005/foodarena-ai/pull/28) 在查询时仍为 open。未见可靠证据把各任务分配给更多具体成员。

**燃尽口径**：Issue 均已关闭，但除 #1 于 9 月 1 日关闭外，其余 25 项集中在 9 月 11 日关闭。仓库未提供逐日剩余工作量或故事点；因此仅列“计划 Issue 数 → 2026-09-11 关闭后剩余数”，不能绘制真实逐日燃尽曲线，也不能把集中关闭时间当作各轮实际完成时间。

**本次分析采用的 DoD 对照项（非历史验收记录）**：代码进入仓库、与 Pydantic/API 契约一致、Mock 可离线测试、后端 `ruff`/`pytest` 和前端 `lint`/`typecheck`/`vitest`/`build` 通过、文档及安全边界同步更新。此处“有 CI 配置”不等于已核验每次远端运行绿色；各项按当前基线可见代码核对，不能推导各轮历史门禁已通过。

## 来源

- [Sprint 3 Issue 检索](https://github.com/wujiade-2005/foodarena-ai/issues?q=is%3Aissue+%5BS3%5D)
- [提交历史](https://github.com/wujiade-2005/foodarena-ai/commits/main/)
- [CI 配置](https://github.com/wujiade-2005/foodarena-ai/blob/496eb9d82c/.github/workflows/ci.yml)

独立核对入口：[当前服务源码](https://github.com/wujiade-2005/foodarena-ai/blob/496eb9d82c/src/foodarena_ai/service.py)、[接口源码](https://github.com/wujiade-2005/foodarena-ai/blob/496eb9d82c/src/foodarena_ai/main.py)。本报告与其他新增文档均为分析产物，不作为相互证明的依据。
