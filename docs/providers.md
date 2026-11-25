# Models: bring your own

Figwright never ships a key and never proxies your work through a server of
ours, because there isn't one. You point it at a model you pay for, or at one
running on your own machine, or at nothing at all.

There are three roles, set separately:

| Role | What it does | Needs |
| --- | --- | --- |
| `text` | Turns a description into a figure, and edits one from an instruction | Any chat model that can return JSON |
| `vision` | Reads a sketch, a photo of a whiteboard, or a reference figure | A model that accepts images |
| `image` | Draws an illustration as a bitmap (the one place a figure is not vector) | An image model |

Set them in the app under **Settings**, or from the command line:

```bash
figwright config providers              # what can be connected
figwright config set-key anthropic      # the key is read from the prompt or a pipe, never from the command line
figwright config role text anthropic claude-opus-5-5
figwright config role vision anthropic
figwright config show                   # keys are shown masked
```

Keys are stored in `~/.figwright/config.json` (file mode `600` where the
operating system supports it) and are sent to nothing but the provider you
chose. An environment variable of the usual name is used when no key is saved,
so `export ANTHROPIC_API_KEY=…` is enough for a one-off run.

## What can be connected

| Provider | Roles | Environment variable | Notes |
| --- | --- | --- | --- |
| `mock` | text, vision, image | — | Offline demo. No key, no network, no model: text rules and placeholder shapes. This is what you get before you connect anything. |
| `anthropic` | text, vision | `ANTHROPIC_API_KEY` | Native API, streaming |
| `openai` | text, vision, image | `OPENAI_API_KEY` | |
| `gemini` | text, vision, image | `GEMINI_API_KEY` | Native API |
| `deepseek` | text | `DEEPSEEK_API_KEY` | |
| `dashscope` | text, vision | `DASHSCOPE_API_KEY` | Alibaba, Qwen |
| `moonshot` | text, vision | `MOONSHOT_API_KEY` | Kimi |
| `zhipu` | text, vision, image | `ZHIPU_API_KEY` | GLM |
| `siliconflow` | text, vision, image | `SILICONFLOW_API_KEY` | |
| `tokenhub` | text, vision | `TOKENHUB_API_KEY` | Tencent, Hunyuan |
| `qianfan` | text, vision | `QIANFAN_API_KEY` | Baidu, ERNIE |
| `openrouter` | text, vision, image | `OPENROUTER_API_KEY` | |
| `xai` | text, vision, image | `XAI_API_KEY` | Grok |
| `mistral` | text, vision | `MISTRAL_API_KEY` | |
| `groq` | text, vision | `GROQ_API_KEY` | |
| `ollama` | text, vision | — | Local, `http://localhost:11434/v1` |
| `lmstudio` | text, vision | — | Local, `http://localhost:1234/v1` |
| `custom` | text, vision, image | `FIGWRIGHT_CUSTOM_API_KEY` | Anything that speaks the OpenAI API: your lab's gateway, vLLM, a proxy |

Everything except `anthropic`, `gemini` and `mock` speaks the OpenAI chat
format, so a provider that is not on this list is usually just `custom` with its
address filled in.

## Model names are not baked in

Figwright does not hard-code model ids, because they go stale faster than
software. The Settings page asks the provider which models it has
(`POST /api/config/models`) and lets you pick; **Test** sends one short request
so you learn about a wrong key there and then rather than halfway through a
figure. If a provider has no list endpoint, type the id in.

## Running with no model at all

This is a first-class mode, not a broken state. With nothing connected:

- `generate` parses arrows, numbered steps, `if … then …` and `n = …` counts out
  of your sentence, and builds a real flowchart, workflow, pathway, PRISMA
  diagram, abstract or poster from them.
- `refine` understands a list of plain edits (theme, font size, line width,
  title, rename, recolour, delete, connect, add) and tells you so when your
  instruction is outside that list.
- Templates, charts, statistics, the vectorizer, the image lab, linting and
  every export work exactly as they do with a model, because none of them
  involve one.
- Illustrations come out as honest placeholder shapes, marked as such.

Every figure made this way carries `offline demo` in its record, and the
provenance line says that no model was used. Figwright will not quietly fall
back to the demo when a real provider refuses or the network drops: that comes
back as an error, because a figure that silently changed how it was made is
worse than no figure.

## What is sent, and when

| You do | What leaves your machine |
| --- | --- |
| Open the app, draw, edit, lay out a template, chart a table, trace a picture, export | Nothing. The server is on `127.0.0.1` and does the work locally. |
| `generate` / `refine` with a provider connected | Your prompt, the attached source text (clipped), and for `refine` a compact description of the figure. |
| A sketch or reference image | That image, to the `vision` provider. |
| An illustration | Your prompt, to the `image` provider. |
| **Test** on the Settings page | One short request, to that provider. |

No telemetry, no analytics, no "anonymous usage statistics". The app makes no
outbound request that you did not ask for; the page loads no fonts, scripts or
images from anywhere (its content security policy only allows `'self'`).
