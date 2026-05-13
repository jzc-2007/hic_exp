# Decisions

## 2026-05-12

- HIC defaults to local Flask under /hic and stores all coordination state in
  SQLite.
- The runner uses mock mode unless HIC_CODEX_CMD is configured, because the
  exact desired Codex CLI invocation should be explicit.
- Existing kaiming.me deployment is not modified automatically.

## 2026-05-13

- Agent/person names in UI are normalized to readable display format (for
  example `hanhong_zhao` -> `Hanhong Zhao`) while keeping slugs unchanged.
- UTC timestamps shown in UI are rendered as relative time labels (for example
  `2m ago`, `in 3h`) with original ISO timestamp preserved in hover title.
- Added an in-product usage guide route (`/hic/guide`) backed by
  `shared/USAGE.md`.
- `kaiming.me/hic` is served through the existing dashboard reverse proxy and
  inherits the dashboard password gate.
- The default idle wake cadence is 240 minutes. Routine idle status belongs on
  Dashboard/Logs, not in group chat.
- Added `self_evolver` as the fifth agent for HIC self-improvement. It can edit
  this repository and reuses one persistent Codex session history.
- Mirrored `agent_ops/docs/safety_rules.md` into HIC prompt-visible
  `shared/TPU_SAFETY_RED_LINES.md`; any task-running agent must ask before
  TPU-affecting, fresh audit, large data movement, or shared cluster mutation
  commands.
- Updated `main` agent display name to `Kaiming He` (slug remains `main`) per
  PI direct request.
- Updated `self_evolver` agent display name to `jqdai` (slug remains
  `self_evolver`) per PI direct request.
- Added group-chat `@mention` wake fanout: `@agent` now creates immediate wake
  requests for matched enabled agents.
- Added a chat mention picker and `@all` support so PI can select targets from
  the message box instead of remembering slugs.
- Changed group routing so unmentioned group messages wake nobody; `@agent`
  wakes only the mentioned agent, and `@all` wakes all enabled agents.
- Simplified delivery priority to two labels only: `normal` sends without
  waking, while `important` wakes the direct recipient or explicit group
  mention targets (`@agent` / `@all`). Legacy priority values above 2 are
  normalized to `important`.
- Task creation follows the same wake distinction: `normal` tasks do not wake
  the owner, while `important` tasks create an owner wake request.
- Agent replies to group chat are allowed even when there are no active tasks;
  routine idle updates should be prevented by prompt/protocol, not by dropping
  all group outbound messages.
- Agents must keep replies in the source channel. Group messages are answered
  in group; direct/private PI messages are answered in the agent's direct chat.
  The daemon also reroutes accidental PI-direct replies back to group when the
  latest PI prompt came from group.
- Group chat is broadcast-visible to every agent on wake. `@agent` / `@all`
  only control immediate wake targeting, not message visibility.
- Chat is the default coordination surface. Tasks remain available only for
  explicit long-running work orders; Self-Improve routes as incident + direct
  maintainer message instead of creating a routine task.
- Wake requests are coalesced per agent while queued. Once an agent starts a
  run, the claimed wake is cleared from pending; new important messages during
  that run create a fresh follow-up wake.
- All real-runner HIC agents use per-agent persistent Codex sessions via
  `CODEX_SESSION_ID` and `codex exec --json ... resume <session> -` after the
  first wake. This keeps one-time initialization out of routine wakes.
- Real-time inspection belongs in per-agent Progress pages. Logs remain the
  archive/debug surface; Progress polls the latest wake log and presents both
  readable cards and raw streaming output.
