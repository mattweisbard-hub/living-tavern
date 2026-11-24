# Living Tavern

Four NPCs, top-down room, per-browser SQLite saves, memory and relationship inspector. Default demo mode is scripted, not LLM-driven. Autonomous mode advances round-robin while the browser is open.

For local AI, install Python and Ollama, pull qwen2.5:1.5b, install requirements, set MODE=local, and run python app.py. Visit http://127.0.0.1:8000. Default LLM_URL is Ollama's /v1 API. Configure CPU-only inference in Ollama itself.

Render free deployment uses demo mode and ephemeral storage; saves can disappear on restart. No paid inference by default. Hosted mode supports an OpenAI-compatible endpoint via MODE=hosted, LLM_URL, MODEL, and LLM_KEY. Do not enable publicly accessible paid inference without authentication, budget caps and rate limiting. This prototype does not implement production abuse controls.
