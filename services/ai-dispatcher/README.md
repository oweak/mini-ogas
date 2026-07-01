# ai-dispatcher

AI diagnosis gateway with ordered provider fallback.

Responsibilities:

- classify events before calling AI
- deduplicate repeated alerts
- cache common diagnosis results
- try `AI_PROVIDER_CHAIN` in order: DeepSeek, Ollama, LM Studio, Groq
- normalize AI response into structured JSON
- record the serving provider, attempted providers, and safe failure reasons
- send result back to central API

AI must not directly execute high-risk actions.

If every configured provider is unavailable, the dispatcher returns an
explicit `local-fallback` diagnosis rather than pretending an external model
responded.
