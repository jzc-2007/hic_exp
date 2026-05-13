# HIC 使用文档 / Usage Guide

## 1. 快速开始

- 进入项目目录：`cd /home/jzc/zhichengjiang/working/ai_workspace/hic`
- 初始化并启动：
  - `bash scripts/setup.sh`
  - `bash scripts/start_all.sh`
- 公网入口：先打开 `https://kaiming.me`，用现有 dashboard 密码登录，然后点顶部 `HIC`。
- 本机入口：`http://127.0.0.1:18765/hic`；当前有效 URL 也会写入 `var/run/web_url`。
- HIC 顶部菜单里的 `TPU Dashboard` 会回到 `https://kaiming.me/` 的 TPU 任务 dashboard。
- Dashboard 里 `runner real` 表示 agent wake 会真的调用 Codex；`runner mock` 表示只模拟。
- 每个 agent 都复用自己的 Codex session（`agents/<slug>/CODEX_SESSION_ID`），后续 wake 走 `resume`，不需要每次重新初始化。
- `hic_daily_update` 会每天把确定性的系统/agent 状态写入 `shared/DAILY_STATUS.md`，提交并推送到 `git@github-hic-exp:jzc-2007/hic_exp.git`。

## 2. 页面说明

- `Dashboard`：看所有 agent 状态、任务摘要；最近唤醒时间是相对时间，下次唤醒时间是实时倒计时（`hh:mm`）。
- 顶部栏会显示 `Codex tokens: in/out`，来自各 agent 最新 wake 日志里的 usage 汇总（无数据时显示 `-`）。
- `Chat`：给 `group` 或单个 agent 发消息；`normal` 只发送，`important` 才唤醒目标。group 里用 `@agent` / `@all` 明确唤醒对象。右侧 Health 区会显示 `Wake state` 和 `Last PI message`，便于判断 agent 是否已被唤醒并读取消息。
- `Progress`：从 Dashboard 或 direct chat 的 agent 行进入，实时查看该 agent 最新 wake 的 Codex 输出；页面会自动刷新，显示 `working` / `not running`、可读事件卡片，以及结构化 `Live Raw` 流视图（session/turn/usage/command/files/error 标签）+ 可展开的完整原始文本。
- Chat 发送框默认优先级是 `important`（`2`）；需要“只发送不立即唤醒”时手动改成 `normal`（`1`）。
- `Tasks`：少数显式长任务/工单才用；日常协作默认走 group/direct chat。
- `Guide`：当前文档。
- `Ops`：安全运维动作（wake、tests、doctor、restart daemon、reload config）。
- `Logs`：先看人类可读的事件卡片，需要时再展开原始终端细节。
- `Settings`：启停 agent、添加 agent、查看 `config/agents.yaml`。
- `Self-Improve`：提交系统改进请求，自动落到任务和 incident 记录。

## 3. 消息与唤醒机制

- `normal` 消息不会唤醒任何 agent；agent 会在自己的 wake 周期里读取群聊和私信。
- `important` direct 消息会唤醒目标 agent。
- `important` group 消息只有在包含 `@agent` / `@all` 时才会唤醒对应目标。
- 系统默认 priority 是 `important`（`2`）。
- group 消息对所有 agent 可见；`@agent` / `@all` 只决定谁被立即唤醒，不会把消息变成私信，也不会对其他 agent 隐藏。
- 群聊输入框里输入 `@` 会弹出可选 agent；选人后插入 `@slug`。需要全员立即看见时用 `@all` 并选择 `important`。
- daemon 会并行启动不同 agent；同一个 agent 仍由 lock 防重入。
- Task 不是日常入口。一般直接发 group/direct 消息；只有明确需要长期跟踪的工作才创建 task。Task 优先级也只有 `normal` / `important`：`normal` 只记录，`important` 会立即唤醒 owner。
- agent 返回的 `next_wake_minutes` 会被系统 clamp 到最大 240 分钟。
- 发完消息后，消息卡片会显示 `wake queued` / `working` / `wake complete`，并显示哪些 agent 已读。
- 需要看 agent 正在做什么时，点它旁边的 `Progress`；这比 Logs 更适合实时观察，类似看 Codex 正在流式输出。
- Direct 聊天会额外显示所选 agent 的当前唤醒状态（`working` / `awake recently` / `wake queued` / `sleeping`）和最近一条 PI 消息的读取状态。
- agent 回答时会按来源回到同一频道：群聊问题回 group，私聊问题回 direct。
- agent wake 会 resume 自己的 Codex 历史；每次主要读新 group/direct 消息和少量变化文件，不重复做首次初始化。
- 高频重复动作要做成一键命令/脚本并写入文档（比如 `hicctl` / `Makefile`），优先简化路径而不是堆流程。
- 可以上传文件；文件保存在 `var/uploads/`，消息正文会包含本机路径，agent 可以读取。
- idle wake 的状态单独显示在 Dashboard/Logs，不再发 routine group message。

## 4. Self-Improve 和 Self Evolver

- HIC bug、UI 请求、困惑行为、缺少的 workflow，都丢到 Self-Improve。
- 提交后会写入 `shared/INCIDENTS.md`，给 `jqdai` 发 direct message，并 wake 它；不自动创建 routine task。
- `jqdai` 是第 5 个 agent（slug 仍是 `self_evolver`），专门维护 HIC 本身；它可以修改这个仓库。所有 agent 都复用自己的 Codex 历史。

## 5. 时间与名称显示规则

- Chat 消息时间和最近唤醒时间显示为“相对现在”的格式，例如：`2m ago`。
- 下次唤醒时间显示为实时倒计时 `hh:mm`（分钟粒度）。
- 悬浮时间字段可看到原始 ISO/UTC 时间戳（`title` 属性）。
- 人名统一格式化为首字母大写，例如：`Hanhong Zhao`。

## 6. 常用故障处理

- 服务健康检查：`python3 scripts/hicctl.py doctor`
- 查看任务：`python3 scripts/hicctl.py tasks`
- 手动唤醒：`python3 scripts/hicctl.py wake main`
- 查看原始日志：`python3 scripts/hicctl.py logs daemon`
- 跑测试：`python3 scripts/hicctl.py test`
- 压缩 agent 长期记忆：`python3 scripts/hicctl.py compact-notes`（将 `MEMORY.md`/`EXPERIENCE.md` 结构化并控制大小）

## 7. TPU / 任务安全红线

- 规则源头是 `agent_ops/docs/safety_rules.md`，HIC 摘要在 `shared/TPU_SAFETY_RED_LINES.md`。
- 能跑任务的 agent 在 TPU/GPU/cloud 工作前都必须读这些红线。
- 启动/恢复/杀掉/删除/重启/重配 TPU job，提交 dashboard TPU job，运行 `tpu_simple.py run/resume/daemon`，或者跑 `tou --cache false` / `yizhitou`，都需要用户本轮明确授权。
- 大规模跨区数据/ckpt/log 复制、反复探测缺失远程数据、cloud API retry loop、修改共享锁/磁盘/账号配置，也都必须先问。
- 默认用只读/缓存检查；不确定时让 agent 输出拟执行命令和风险标签，而不是直接跑。

## 8. 安全建议

- 现在公网入口通过 `kaiming.me` latest dashboard 的已有密码保护转发到 HIC。
- 不要单独加 Cloudflare `/hic.*` 直连，除非先给 HIC 配 `HIC_UI_TOKEN` 或同等级访问控制。
- Ops 里的动作是 allowlisted，但真实 Codex runner 可以在 agent 被指派时修改文件或执行工作；重要目标请写进 task。
