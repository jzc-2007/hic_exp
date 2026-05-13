# Incidents And Improvements

Improvement requests submitted in the UI are appended here and mirrored into
the tasks table.

## 2026-05-12T23:53:07+00:00 UX issue: 名字写成Hanhong Zhao这种格式，然后把UI改的赛博朋克一点，加上使用文档；另外，那些UTC时间都改成距离现在的相对时间 task_id=1

名字写成Hanhong Zhao这种格式，然后把UI改的赛博朋克一点，加上使用文档；另外，那些UTC时间都改成距离现在的相对时间

Resolution (2026-05-13T00:01:03+00:00):
- Completed in task #1.
- Implemented readable name formatting, cyberpunk UI refresh, relative-time rendering, and `/hic/guide` usage documentation.

## 2026-05-13T00:55:26+00:00 PI direct request: 请把你的名字改成kaiming he task_id=2

你好，你能看到自己是怎么运行的吗？请把你的名字改成kaiming he

Resolution (2026-05-13T00:57:18+00:00):
- Completed in task #2.
- Updated `config/agents.yaml` so `main` display name is `Kaiming He`.
- Synced agent records to SQLite and prepared a direct confirmation reply to PI.

## 2026-05-13T01:01:25+00:00 PI direct request: 把self-evlover的名字改成jqdai，然后你完成任务给我回复 task_id=3

把self-evlover的名字改成jqdai，然后你完成任务给我回复

Resolution (2026-05-13T01:06:07+00:00):
- Completed in task #3.
- Updated `config/agents.yaml` so `self_evolver` display name is `jqdai`.
- Synced agent records to SQLite and prepared a direct confirmation reply to PI.

## 2026-05-13T01:51:21+00:00 PI direct request: 群聊支持 @ 功能并立即唤醒被提及 agent task_id=4

你让群聊有@功能，@到的人立马被叫醒

Resolution (2026-05-13T01:56:27+00:00):
- Completed in task #4.
- Added group-chat mention parsing in `hic/message_bus.py`; `@agent` now wakes matched enabled agents immediately.
- Superseded wake semantics: `normal` now sends without wake; `important` wakes only the direct recipient or explicit `@agent` / `@all` group targets.
- Added test coverage in `hic/tests/test_message_bus.py` and updated chat/help documentation.
