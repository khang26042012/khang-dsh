# DSH Prompt Kit (MIT)

Bo text prompt trich tu DeepSeek Harness (license MIT - duoc phep tai su dung).

## Cau truc system prompt goc (theo thu tu order):
1. order -100  identity:    "You are an AI agent powered by <harness name>."
2. order 0     persona:     config.persona (ban tu viet persona rieng cua ban)
3. cac section tool/plugin dang ky tiep theo (dsh-tools, web, goals...)
4. order 99    collapse:    "Tools in [group] collapse..." (dsh-tools)

## File nao chua gi:
- dsh-tools.txt           -> TOAN BO quy tac run_code/tool docs (phan "ngon" nhat)
- dsh-system-prompt.txt   -> dong co render template {{variable}} + section engine
- dsh-compaction-basic.txt-> prompt nen/checkpoint cuoc tro chuyen
- dsh-subagent.txt        -> prompt uyen quyen subagent/workflow
- dsh-app-boot.txt        -> runtime context, checkout path...
- dsh-web-app.txt         -> huong dan Web GUI
- con lai                 -> jobs/ralph/reminder/plan-mode

## Cach reuse trong agent rieng:
1. Copy khoi text phu hop vao system prompt cua ban (giu nguyen hoac viet lai ten tool).
2. Thay ten tool (run_code/read/edit/glob/grep...) bang tool that cua ban.
3. Persona: tu viet vi tri "You are X..." - day la phan platform tiem vao, khong nam trong kit.
4. Giu nguyen tinh than: mo ta HAU QUA + CON DUONG thay vi menh lenh chung chung.

Sinh tu package @deepseek-ai/dsh version 0.1.0-rc.6.
