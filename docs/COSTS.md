# Running costs

Nothing paid is active. Each item below is switched on only after HAYAH approves it.

| Item | Status | Expected monthly cost |
| --- | --- | --- |
| VPS (2 vCPU / 4 GB) | Approved in principle, not purchased | ~$10–25 |
| Domain/HTTPS | Reuse HAYAH's domain; Caddy/Let's Encrypt is free | $0 |
| Google Sheets / Drive API | Free API; uses existing Google storage | $0 (storage upgrade only if Drive fills up) |
| WhatsApp Cloud API | Receiving team messages is free; template notifications are charged per message by Meta, by country | $0 for intake; notifications priced before activation |
| Anthropic API | Off. Cap set to $100/month (editable in Settings) | ≤ $100, enforced by the system |
| Software licences | All open source | $0 |

## Claude Pro vs Anthropic API

Claude Pro covers people chatting with Claude and Claude Code development. It does
**not** include API credits. Automated processing uses the Anthropic API, billed
per token (input and output priced separately per model) on a separate account
owned by HAYAH. The system:

- records every AI call in `usage_records` with its estimated cost,
- stops calling the API when the monthly budget is reached and falls back to the
  free rules engine + AI Review queue (nothing stops working),
- sends only text and a few extracted video frames, never whole videos.

A per-message cost estimate with current Anthropic prices is produced in Phase 6
before the API is switched on.
