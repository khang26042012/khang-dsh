# KHANG HARNESS — BLUEPRINT LAP RAP 🐭

Tai lieu chi cach bien nguon lieu trong repo nay thanh mot AI agent hoan chinh.

## 1. BAN DO KIEN TRUC DSH GOC (dao tu source that)

    dsh/lib/bin.js  (CLI: "dsh web --host --port --profile")
        |
        v
    @deepseek-ai/cordis  (khung plugin: Service, ctx, plugin loader)
        |
        +-- dsh-settings-file -----> doc settings.yaml (watch chokidar, reload nong)
        +-- dsh-llm-pi-ai ----------> adapter cau hinh provider/model trong settings.yaml
        |       |
        |       v
        |   earendil-works/pi-ai --> driver LLM thuc su (openai-completions,
        |                            anthropic-messages, google, mistral, bedrock)
        +-- dsh-system-prompt ------> dong co lap prompt theo section co order
        +-- dsh-tools --------------> dang ky tool run_code/read/edit/glob/grep...
        +-- dsh-web-app ------------> server GUI + inject window.__DSH_BOOT__
        +-- dsh-client-connection -> WebSocket mux tai /api/events.mux
        +-- dsh-agent / agent-loop -> vong lap: model -> tool call -> ket qua -> model
        +-- dsh-session-* ---------> luu/phuc hoi phien
        +-- dsh-compaction-basic --> nen/checkpoint khi dai qua han

## 2. DUONG DANH NGAN NHAT DE TU BUILD ("Khang Harness" toi thieu)

Buoc 1: Driver LLM — dung truc tiep pi-ai (doc lap):
    import { stream } from 'pi-ai/dist/api/openai-completions.js'
    // hoac dung muc cao hon cua no neu muon da-nha-cung-cap

Buoc 2: Vong lap agent (pseudo):
    const messages = [{ role:'system', content: SYSTEM_PROMPT }]
    while (true) {
      const reply = await stream(model, messages, tools)
      if (reply.toolCalls) { for (tc of reply.toolCalls) {
          const result = await executeTool(tc)     // read/write/bash cua ban
          messages.push(toolResult(tc.id, result))
      }} else break
    }

Buoc 3: System prompt — ghep tu dsh-prompt-kit/:
    identity (-100) -> persona (0) -> tool rules -> runtime context -> collapse (99)
    Thay ten tool cho khop voi tool cua ban.

Buoc 4: Tool cua ban — tham khao chuan tu dsh-tools.txt:
    - Mo ta HAU QUA + CON DUONG (vi du: "a FAILED call rejects with ToolCallError")
    - Khai bao input schema JSON de model goi chuan

Buoc 5 (nang cap): GUI — copy y tuong dsh-client-connection:
    1 ket noi WebSocket /api/events.mux da-plex ca chat + tool events + state

## 3. MAP FILE TRONG REPO -> CHUC NANG

    dsh-src/earendil-works-pi-ai/   -> driver LLM (quan trong nhat, doc lap duoc)
    dsh-src/deepseek-ai-dsh-tools/  -> chuan tool schema + prompt quy tac
    dsh-prompt-kit/*.txt            -> toan bo text prompt goc de chep lai
    dsh-src/dsh-main-config/        -> config mac dinh (agent presets...)
    dsh-src/deepseek-ai-dsh-*       -> 195 plugin con lai de tham khao nang cap

## 4. QUY UOC GOC DANG CHU Y (bat gap tu source)

- Section prompt co so thu tu; sap xep sai = prompt xau ma khong bao loi.
- Settings co watcher file (chokidar, debounce 100ms) — sua file la reload nong,
  nhung mot so doi tuong resolve mot lan per-session nen can chat moi.
- Model metadata "input: [text, image]" trong settings.yaml quyet dinh
  gate read_image + viec giu/huy anh khi gui di.
- Contents API GitHub: PUT song song 8 luong vao 1 nhanh = 409; 2 luong + retry ok.

## 5. LICENSE
Nguyen bo goc MIT (@deepseek-ai). Giu dong ghi nho ban quyen khi tai su dung.
