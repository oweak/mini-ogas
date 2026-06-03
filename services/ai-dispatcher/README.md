# ai-dispatcher

AI diagnosis gateway for DeepSeek.

Responsibilities:

- classify events before calling AI
- deduplicate repeated alerts
- cache common diagnosis results
- call DeepSeek API
- normalize AI response into structured JSON
- send result back to central API

AI must not directly execute high-risk actions.

