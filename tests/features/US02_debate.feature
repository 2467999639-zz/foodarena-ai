#language: zh-CN
功能: 三轮双 Agent 辩论
  作为用户
  我希望看到川辣派与粤式养生派有序轮流发言
  以便获得透明而非黑盒的推荐过程

  场景: Mock 流程生成六条交替消息
    当 会话处于 RUNNING 状态并执行轮次控制器的 Mock 流程
    那么 两个 Agent 交替完成 3 轮共 6 条消息
    并且 同一 Agent 不连续发言
    并且 每条消息包含 round、agent、argument 与 evidence
    并且 会话状态推进到 VALIDATING

  场景: 重复启动不产生第二条执行链
    当 会话已完成辩论并再次调用启动接口
    那么 返回当前 SUCCESS 状态且消息数量仍为 6
