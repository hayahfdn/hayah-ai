# Floating assistant (2026-11-19)

A «المساعد» button on every page, for every role, on the opposite side from «عدّل بكتابة طلب».
It explains how to use the system in Arabic or English. It is read only: it has no tool that
changes data.

- **Knowledge:** `backend/app/system_guide.md`. Update it when a page or a rule changes. Parts after
  `<!-- section: managers -->` reach managers only.
- **Lookups:** it can look up one well by number (and, for managers, one sacrifice) with the same
  rules as the pages: cost only for managers, contractors only their own wells, never phone numbers.
- **Cost:** same Anthropic key and the same monthly AI budget (20 USD) as the prompt box. Each answer
  is recorded in usage as `help_chat`. When the key is missing, AI is off or the budget is used up, the
  panel says so in plain words.
- **API:** `GET /api/help/status`, `POST /api/help/ask` (`{messages, page}`), all signed-in roles.
- **Button:** press and hold to move it, like the prompt button; the place is saved per user and device.
- Tests: `backend/tests/test_help_chat.py`.
