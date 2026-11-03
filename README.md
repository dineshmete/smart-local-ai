# Smart Local AI

A local multi-model router for [Open WebUI](https://github.com/open-webui/open-webui) running on [Ollama](https://ollama.com). You chat with one model called **Smart Router**. It looks at each question and sends it to the right local model: a fast model for short chats, a reasoning model for math and logic, and a general model for everything else, including code, files, images and live questions.

The project is a single Open WebUI **Pipe function** (`smart_router.py`) plus three workspace models.

## What it does

- **Routing:** Keyword rules first. If no keyword matches, a small model classifies the question as `live`, `code`, `math`, `general` or `chat`.
- **Quick Chat** (`gemma2:2b`): very short messages and greetings.
- **Deep Reasoning** (`deepseek-r1:7b`): calculations, math and logic.
- **Smart Assistant** (`qwen2.5:7b-instruct`): general questions, code, files and images, and live questions.
- **Live questions:** DuckDuckGo search (via `ddgs`), then the router reads the text of the top pages and gives it to Smart Assistant. Weather questions detect the city name and fall back to `DEFAULT_CITY`.
- **Date and time:** Answered directly from the server clock, without search or a model.
- **Follow-ups:** Short follow-up questions such as "what about yesterday?" are searched together with the previous question.
- **Language:** Replies in the same language or script as the user. Roman Hinglish gets Roman-letter replies.
- **Fallback:** If the chosen model fails, the router uses Quick Chat.

## Limitations

- Answers depend on small local models and DuckDuckGo results. They are not as accurate or as deep as large cloud models such as Gemini.
- Routing by keywords can send some questions to the wrong model.
- Live answers are only as good as the search results and the pages the router can read.
- Code is written by the model, not run. The router does not execute code.
- Speed depends on your hardware. Deep Reasoning is the slowest model.

## Requirements

- Windows, macOS or Linux with [Ollama](https://ollama.com) installed
- Open WebUI (desktop app or server)
- Python 3.11+ (the Python that Open WebUI uses)
- Enough RAM for a 7B model (about 8 GB or more recommended)

## Setup

### 1. Pull the models

```bash
ollama pull gemma2:2b
ollama pull deepseek-r1:7b
ollama pull qwen2.5:7b-instruct
```

### 2. Install the Python libraries

```bash
python -m pip install ddgs httpx
```

### 3. Create three workspace models in Open WebUI

Go to **Workspace > Models > Create** and make these models:

| Display name | Model ID | Base model | Notes |
|---|---|---|---|
| Quick Chat | `fast-chat` | `gemma2:2b` | Short replies, 1–3 sentences |
| Deep Reasoning | `reasoning` | `deepseek-r1:7b` | Step-by-step, ends with `Answer:` |
| Smart Assistant | `smart-assistant` | `qwen2.5:7b-instruct` | Capabilities: Vision, File Upload, File Context, Web Search, Citations |

Suggested parameters for Smart Assistant: temperature `0.5`, max tokens `1500`, `num_ctx` `4096`, `keep_alive` `15m`.

### 4. Add the router function

1. In Open WebUI, go to **Admin > Functions > Create**.
2. Paste the contents of `smart_router.py` and click **Save**.
3. Turn the function on (toggle ON).
4. Open the function's **Valves** if you want to change the defaults.

### 5. Use it

Start a new chat, choose **Smart Router** from the model menu, and ask a question.

## Valves (settings)

| Valve | Default | What it does |
|---|---|---|
| `ID_FAST` | `fast-chat` | Quick Chat model ID |
| `ID_REASON` | `reasoning` | Deep Reasoning model ID |
| `ID_SMART` | `smart-assistant` | Smart Assistant model ID |
| `SEARCH_RESULTS` | `5` | Search results per live question |
| `PAGE_READS` | `2` | Number of top pages whose text is read |
| `DEFAULT_CITY` | `Pune` | City used when a weather question has no city name |
| `LIVE_WORDS` | (list) | Keywords that mark a question as live |
| `CODE_WORDS` | (list) | Keywords that send a question to Smart Assistant as code |
| `REASON_WORDS` | (list) | Keywords that send a question to Deep Reasoning |
| `GENERAL_WORDS` | (list) | Keywords that send a question to Smart Assistant as general |
| `SHOW_ROUTE` | `True` | Show which model was chosen in the chat status line |

Valve values saved in Open WebUI do not update automatically when the code changes. Check them after you save a new version.

## Test questions

- `kya time hai` → Quick Chat (server time, no search)
- `pune mein kaun sa mausam hai` → Smart Assistant with search
- `python me list sort kaise karte hai` → Smart Assistant
- `5 + 3 * 2 kitna hota hai` → Deep Reasoning

## Files

- `smart_router.py`: the Open WebUI Pipe function
- `LICENSE`: MIT

## Roadmap

- Benchmark response times on common hardware
- Better classification with a dedicated small model
- Optional code execution with a safe sandbox

## License

MIT
