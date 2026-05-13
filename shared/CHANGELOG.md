# Changelog

## 2026-05-12

- Created Milestone 1 HIC implementation scaffold.
- Implemented SQLite persistence, daemon, mock-compatible runner, CLI, Flask
  web UI, tmux scripts, doctor checks, tests, and test report.
- Started HIC in `hic_daemon` and `hic_web`; web selected fallback port 18765
  because the existing TPU dashboard owns 8765.

## 2026-05-13

- Fixed PI-reported UX issue #1:
  - standardized readable person-name display format in UI.
  - switched wake/chat timestamp rendering from raw UTC to relative time.
  - introduced a cyberpunk visual refresh for the web frontend.
  - added operator usage guide page (`/hic/guide`) and source doc
    (`shared/USAGE.md`).
- Updated wake UX from PI follow-up:
  - changed next-wake UI text from coarse relative labels (for example
    `in 3h`) to live `hh:mm` countdown values (minute granularity).
- Updated wake visibility from PI follow-up:
  - added explicit agent wake-state labels (`awake`, `awake recently`,
    `waking up`, `sleeping`) in Dashboard/Chat health views.
  - added a direct-chat "Last PI message" status line so PI can see whether
    the selected agent has read the latest message and whether wake is queued.
  - simplified message delivery to `normal` (send only) and `important`
    (wake target); removed urgent/group priority fanout semantics.
  - aligned task creation with the same two labels: normal records a task,
    important records it and wakes the owner.
  - fixed agent outbound handling so legitimate group replies are no longer
    suppressed just because the agent has no active task.
  - clarified channel routing for agent replies and added a daemon safeguard:
    answers to group-origin PI messages stay in group even if the runner emits
    `recipient: "pi"`.
  - documented that group `@` mentions affect wake targeting only; all agents
    can still see group messages when they wake.
  - simplified the task model: chat is the default coordination path, tasks are
    optional explicit work orders, and Self-Improve no longer creates routine
    tasks.
  - coalesced wake requests per agent and clear claimed wake requests when a
    run starts, so the UI shows a single queued/running state instead of a
    pile of pending wake counts.
  - switched every real-runner agent to a per-agent persistent Codex session,
    using Codex resume after the first wake instead of only doing this for
    `self_evolver`.
  - added per-agent live Progress pages and JSON endpoints so an operator can
    watch the latest wake log update in near real time from Dashboard/Chat.
  - changed real runner logging to stream output into the wake log while the
    agent is still running, so long wakes have visible progress.
  - added a top-menu `TPU Dashboard` link in HIC that returns to
    `https://kaiming.me/`.
- Updated `main` display name to `Kaiming He` in `config/agents.yaml` and
  synced the agent record in SQLite after PI direct message #20.
- Updated `self_evolver` display name to `jqdai` in `config/agents.yaml` and
  synced the agent record in SQLite after PI direct message #21.
- Changed daemon scheduling so different agents wake in parallel background
  workers, reduced polling to 1 second, and added explicit sleeping / waking
  up / awake state labels to Dashboard and Chat.
- Set PI-facing default priority in Chat/Task creation forms to
  `important` (`2`) and aligned web handler fallbacks to the same default.
- Added a topbar Codex token usage badge that summarizes input/output tokens
  from the latest `turn.completed` usage event per agent wake log.
- Improved Progress readability by parsing structured Codex wake events into
  human cards (session/turn status, token usage, command completion, file
  updates, and runner errors) while preserving AGENT_RESULT summary cards.
- Improved the Progress `Live Raw` panel readability with a structured
  streaming view (line-numbered rows with session/turn/usage/command/files/error
  tags), plus wrap toggle and collapsible full raw text.
- Added global simplicity/self-evolution guidance for all agents:
  - recurring workflows should be turned into one-click helpers;
  - durable memory must stay structured and size-bounded.
- Added `python3 scripts/hicctl.py compact-notes` (and `make compact-notes`) to
  compact agent `MEMORY.md` / `EXPERIENCE.md` into structured, bounded notes.
- Added README guidance for deploying a fresh HIC instance without carrying old
  runtime history or old Codex session files.
- Updated topbar metric from `Codex tokens` to `Codex /status`:
  - primary source is live Codex `/status` output (cached briefly);
  - fallback remains latest wake-log usage summary when `/status` is unavailable.
- Initialized git mirror support for `git@github-hic-exp:jzc-2007/hic_exp.git`
  and added a deterministic daily status updater service.
- Fixed Progress page layout so the live raw stream gets a wider, responsive
  panel and no longer squeezes command/JSON text into a narrow column.
- Changed the Progress side stream from JSON-shaped rows to a readable
  `Live Codex` terminal-style view; raw JSON remains available on demand.
- Limited the deterministic daily status pusher to stage only
  `shared/DAILY_STATUS.md`, avoiding accidental runtime or scratch-file commits.
- Added a HIC self-restart guard: agents must ask the outer operator for HIC
  restarts instead of stopping their own daemon/web process mid-wake.
- Added a runner fallback that turns unstructured Codex `agent_message` output
  into a normal PI chat reply when AGENT_RESULT_JSON is missing or malformed.
- Fixed chat wake badges so only the latest wake message for a running agent
  shows `working`, and message IDs are matched exactly instead of by substring.
- Added repo-level Codex guidance (`AGENTS.md`) plus repo skills:
  `hic-workflow` for self-evolution/PI clarification and `tpu-safety` for
  TPU/cloud red-line checks.
- Added lightweight "grill me" support: agents can return `questions_to_ask`,
  HIC sends those to PI, and the UI marks the agent as `needs input`.
