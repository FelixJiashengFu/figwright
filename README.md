<div align="center">

# Figwright · 图匠

**An open-source figure workshop for research papers. Runs on your machine, uses your model, keeps every figure editable.**

[![tests](https://github.com/FelixJiashengFu/figwright/actions/workflows/ci.yml/badge.svg)](https://github.com/FelixJiashengFu/figwright/actions/workflows/ci.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)

[中文](#中文) · [English](#english) · [Templates](docs/templates.md) · [Models](docs/providers.md) · [MCP](docs/mcp.md)

</div>

---

<a name="中文"></a>

## 中文

科研作图的麻烦不在于画，而在于改：审稿人要你把第三个框改成绿色、把图做成单栏 89 mm、把统计检验补上，而你手里只有一张 PNG。

Figwright 的立场很简单：**图从头到尾是可编辑的数据**。一张图就是一份场景 JSON，浏览器里画它的是 JavaScript，导出时画它的是 Python，两份渲染器在 CI 里逐个小数点对账。导出的 SVG 把场景原样带在身上，所以把 SVG 再拖回来就能继续改；导出的 PPTX 里每个方框是真方框、每段字是真文字、每张图表是 PowerPoint 原生图表，不是图片。

模型是你自己的。Figwright 不带 key、不设中转服务器，也没有「免费额度」：你接 Claude、GPT、Gemini、DeepSeek、通义、Kimi、GLM、文心、混元，或者 Ollama / LM Studio 跑在自己机器上，都行。一个都不接也能用——离线模式用文字规则解析「采样、提取、质检，如果合格则测序，否则重新提取」这种句子，照样生成真正的流程图，并且在图的记录里写明「没有用模型」。

### 装上就能跑

双击就行：macOS / Linux 双击 `start.command`，Windows 双击 `start.bat`。第一次会在同目录建一个独立的虚拟环境装依赖（几分钟，仅一次），之后一两秒就起来，浏览器自动打开。

喜欢命令行：

```bash
git clone https://github.com/FelixJiashengFu/figwright.git
cd figwright
pip install -e ".[mcp]"
figwright                      # 打开应用（127.0.0.1，只听本机）
figwright doctor               # 检查依赖是否齐全
```

接模型（key 从提示或管道读，不走命令行参数，免得留在 shell 历史里）：

```bash
figwright config providers
figwright config set-key anthropic
figwright config role text anthropic claude-opus-5-5
```

### 它能做什么

**出图的四条路**

- **描述成图**：一句话或一段方法描述 → 流程图、实验流程、信号通路、图文摘要、学术海报、PRISMA 2020 筛选流程图。也可以附上 PDF / DOCX / Markdown / 纯文本，让它从文档里取内容。
- **草图成图**：手画草图或白板照片，先用轮廓检测认出方框和箭头，再交给视觉模型整理成规整的图。
- **表格成图**：CSV / TSV / XLSX / JSON → 柱状、折线、散点、箱线、小提琴、直方、热图、饼图、火山图；误差线（SD / SEM / 95% CI）、组间检验、显著性连接线、回归拟合，并自动生成一句可以直接放进图注的方法描述。
- **模板排版**：把你已有的结构化内容（JSON）直接排版，不经过模型，同样的输入永远给同样的图。见 [docs/templates.md](docs/templates.md)。

**编辑器**（浏览器里，纯原生 JS，没有构建步骤）

拖拽、对齐、吸附、多选、图层、撤销重做、连接线自动绕行、五套主题配色（含色盲友好 Okabe-Ito）、批注、版本历史、项目管理、中英界面切换。还有一个排版检查器，专挑重叠、文字出框、连线穿过方框这类毛病，并能一键修。

**图像实验室**

位图矢量化（颜色分层描摹成可编辑路径）、照片/凝胶扫描清理（匀光、白底、去噪、锐化、去背景、裁白边、超分）、按毫米和 dpi 设定印刷尺寸。

**导出**

SVG（带场景，可再编辑）、PPTX（真形状、真文字、原生图表）、PNG / JPEG / TIFF / WebP（指定 dpi 或 89/120/183/254 mm 期刊栏宽）、PDF、单文件 HTML 分享页、JSON。每张图带一份「谁画的」记录：哪个模型、哪一步、什么时候，PPTX 里写在备注页。

**给 AI 助手用**

内置 MCP 服务器，Claude / Codex / 其他 MCP 客户端可以直接调用 11 个工具来作图。读文件的范围是刻意收窄的：只读家目录、当前目录和输出目录下的普通文件，不读隐藏文件、不跟软链接、上限 40 MB，什么都不执行。见 [docs/mcp.md](docs/mcp.md)。

### 对照 FigureLabs 宣称的功能

这个项目是照着 figurelabs.ai 对外宣称的功能清单做的开源替代。名字、界面、文案、图标全部原创，没有照搬它的任何内容。下面是逐条对照，没做到的地方直说：

| 它宣称的 | Figwright | 说明 |
| --- | --- | --- |
| 文字生成插图 | ✅ | 向量图元用场景模型生成；写实插画走 image 模型，没接时给占位图形并标注 |
| 草图生成图 | ✅ | 轮廓检测 + 视觉模型 |
| 流程图 | ✅ | 判断框、是/否分支、回环、上下或左右排版 |
| 数据作图 + 对话改图 | ✅ | 九种图型、三种误差线、参数/非参数检验、Holm 校正、Tukey HSD、回归拟合 |
| 学术海报 | ✅ | A 系列竖版，2/3/4 栏，自动选字号把内容塞进一页 |
| 图文摘要、信号通路、PRISMA、实验流程、医学插画模板 | ✅ | 六个结构化模板 + 医学插画风格 |
| 输入：文字、草图、照片、Excel、PDF、参考图 | ✅ | PDF / DOCX / Markdown / 文本 / CSV / TSV / XLSX / JSON / 位图 |
| 图层编辑器 | ✅ | |
| AI 重绘局部 | ✅ | 选中元素重画 |
| 去背景 | ✅ | 本地算法，不用模型 |
| 无损放大 | ⚠️ | Lanczos 重采样 + 锐化，不是生成式超分，所以不会凭空长出细节 |
| 导出 PPTX / SVG / PNG / JPG | ✅ | 另有 TIFF / WebP / PDF / HTML / JSON |
| 分享链接 | ⚠️ | 给的是单文件 HTML，双击就能看、能邮件发；没有服务器就没有链接——这是设计选择 |
| 风格一致性 | ✅ | 可锁定一套 house style，新图沿用 |
| 批注 | ✅ | 批注跟着图走，PPTX 里进备注页 |
| 「授权证书」PDF | ⚠️ | 做成 AI 使用披露页（哪个模型、哪一步、什么时候），期刊问起来可以直接附。不签名、不发证书：谁也没资格给谁发 |
| MCP（ChatGPT / Claude / Codex） | ✅ | 11 个工具 |
| 订阅、积分、团队席位 | ❌ | 本来就不该有 |

### 它做不到什么

说清楚比好听重要：

- **离线模式不是模型**。它认得箭头、编号步骤、`如果……则……`、`n = …` 这些写法，超出范围会明确告诉你，而不是硬猜。
- **真实模型的输出没有在 CI 里测过**。模型接口是对着本地假服务器测的（各家协议、流式、报错、超时），没有用任何真 key 跑过。接上去第一次用，请自己点一下 Settings 里的「测试」。
- **PPTX 没有在真的 Microsoft PowerPoint 里打开过**。导出结果用 python-pptx 重新读回来逐个形状核对过，也用 LibreOffice 渲染看过。Windows 上第一次用，建议拿一张图试试。
- **引擎的提示信息默认是英文**。界面是中英双语的，但引擎返回的提示（比如「有 3 个值是 0 或负数，取对数后画不出来」）要在 `web/notes.js` 里逐条加翻译；没加到的会原样显示英文。
- **写实插画依赖 image 模型**。没接 image 模型时，插画是程序生成的占位图形，并且在图上标明。
- **海报是排版，不是设计**。它保证内容塞得进一页、字号一致、栏宽整齐；它不会替你想视觉创意。
- **统计是工具，不是审稿人**。它会提醒样本太小、数据可能非正态、分组恒定导致检验无意义，但选哪个检验、能不能这么比，是你的判断。

### 开发

```bash
pip install -e ".[dev]"
python -m pytest -q          # 563 项
```

测试里有一项值得一提：`tests/test_parity.py` 会用 node 跑一遍 JavaScript 渲染器，和 Python 渲染器在七个场景、约一万两千个格式化数值上逐一对账。两份渲染器只要有一处不一致就红。没装 node 时这项自动跳过。

欢迎 PR。改渲染相关的代码请让对账测试通过；加离线解析规则请连带加测试，那部分全靠例子撑着。

---

<a name="english"></a>

## English

The hard part of a paper figure is not drawing it, it is changing it. A reviewer
asks for the third box in green, the figure at 89 mm single-column width, and
the group comparison added — and all you have is a PNG.

Figwright takes one position: **a figure is editable data, from beginning to
end.** A figure is a scene in JSON. The browser draws it in JavaScript, every
export draws it in Python, and CI diffs the two renderers to the last decimal.
An exported SVG carries the scene inside it, so dropping the SVG back in
continues where you left off. An exported PPTX has real shapes, real text, and
native PowerPoint charts — not a picture of a chart.

The model is yours. Figwright ships no key, runs no proxy server, and has no
free tier: point it at Claude, GPT, Gemini, DeepSeek, Qwen, Kimi, GLM, ERNIE,
Hunyuan, or at Ollama / LM Studio on your own machine. Connect nothing and it
still works: offline mode parses sentences like *"collect samples, extract RNA,
if QC passes then sequence, otherwise extract again"* into a real flowchart, and
writes "no model was used" into the figure's record.

### Install

Double-click `start.command` (macOS, Linux) or `start.bat` (Windows). The first
run builds a private virtual environment beside the file and installs what is
needed — a few minutes, once. After that it starts in a second and opens your
browser.

Or:

```bash
git clone https://github.com/FelixJiashengFu/figwright.git
cd figwright
pip install -e ".[mcp]"
figwright                      # the app, on 127.0.0.1 only
figwright doctor               # check the installation
```

Connect a model (the key is read from a prompt or a pipe, never from the command
line, so it stays out of your shell history):

```bash
figwright config providers
figwright config set-key anthropic
figwright config role text anthropic claude-opus-5-5
```

### What it does

**Four ways to a figure**

- **Describe it.** A sentence or a methods paragraph becomes a flowchart,
  experimental workflow, signalling pathway, graphical abstract, conference
  poster or PRISMA 2020 flow diagram. Attach a PDF, DOCX, Markdown or text file
  and it reads the content from there.
- **Sketch it.** A hand sketch or a photo of a whiteboard: contour detection
  finds the boxes and arrows, then a vision model tidies them into a real
  figure.
- **Chart it.** CSV / TSV / XLSX / JSON into bar, line, scatter, box, violin,
  histogram, heat map, pie or volcano plots, with error bars (SD / SEM / 95% CI),
  group comparison, significance brackets and regression fits — plus a methods
  sentence you can paste straight into the legend.
- **Lay it out.** Structured content you already have, laid out by a builder
  with no model involved: same input, same figure, every time. See
  [docs/templates.md](docs/templates.md).

**The editor** (in the browser, plain ES modules, no build step): drag, align,
snap, multi-select, layers, undo/redo, connectors that route around obstacles,
five themes including colour-blind-safe Okabe-Ito, comments, version history,
projects, and a layout linter that finds overlaps, clipped text and connectors
crossing boxes, and fixes what can be fixed.

**The image lab**: bitmap vectorizer (colour-layer tracing into editable
paths), photo and gel-scan clean-up (even out lighting, whiten paper, denoise,
sharpen, remove background, trim margins, upscale), and print sizing in
millimetres at a chosen dpi.

**Exports**: SVG (with the scene inside, reopenable), PPTX (real shapes, real
text, native charts), PNG / JPEG / TIFF / WebP at a dpi or a journal column
width (89 / 120 / 183 / 254 mm), PDF, a single-file HTML share page, and JSON.
Every figure carries a record of which model did which step and when; in a PPTX
it goes in the speaker notes.

**For AI assistants**: a built-in MCP server with 11 tools. File reading is
deliberately narrow — regular files under your home, working or output folder
only, no hidden files, no symlinks, 40 MB cap, and nothing is ever executed.
See [docs/mcp.md](docs/mcp.md).

### Against the feature list FigureLabs advertises

This is an open-source alternative built from the feature list figurelabs.ai
advertises. The name, interface, wording and icons here are original; none of
their text, images or branding was copied. Line by line, including the parts
that fall short:

| Advertised | Figwright | Notes |
| --- | --- | --- |
| Text to illustration | ✅ | Vector figures from the scene model; realistic illustration goes to an image model, with marked placeholders when none is connected |
| Sketch to figure | ✅ | Contour detection plus a vision model |
| Flowcharts | ✅ | Decisions, yes/no branches, loops back, top-down or left-right |
| Data to chart, refine by chat | ✅ | Nine chart kinds, three error types, parametric and non-parametric tests, Holm correction, Tukey HSD, regression fits |
| Posters | ✅ | A-series portrait, 2/3/4 columns, font size chosen to fit one sheet |
| Graphical abstract, pathway, PRISMA, workflow, medical illustration templates | ✅ | Six structured builders plus a medical illustration style |
| Inputs: text, sketch, photo, Excel, PDF, reference image | ✅ | PDF / DOCX / Markdown / text / CSV / TSV / XLSX / JSON / bitmaps |
| Layer editor | ✅ | |
| AI redraw of a selection | ✅ | |
| Background removal | ✅ | Local algorithm, no model |
| Lossless upscaling | ⚠️ | Lanczos resampling and sharpening, not generative: it will not invent detail that was not there |
| Export PPTX / SVG / PNG / JPG | ✅ | Also TIFF / WebP / PDF / HTML / JSON |
| Share link | ⚠️ | A single HTML file instead: double-click it, email it. No server, so no link — that is the point |
| Style consistency | ✅ | Lock a house style; new figures follow it |
| Comments | ✅ | They travel with the figure, and land in PPTX speaker notes |
| "Authorization certificate" PDF | ⚠️ | An AI-use disclosure page instead (which model, which step, when), ready to attach when a journal asks. No signature, no certificate: nobody is in a position to certify anyone |
| MCP for ChatGPT / Claude / Codex | ✅ | 11 tools |
| Subscriptions, credits, team seats | ❌ | Not a feature |

### What it cannot do

Stated plainly, because that is more useful than sounding good:

- **Offline mode is not a model.** It understands arrows, numbered steps,
  `if … then …` and `n = …` counts, and says so when your request is outside
  that list rather than guessing.
- **Real providers are not exercised in CI.** Each dialect is tested against a
  local fake server (protocol, streaming, errors, timeouts); no real key has
  ever been used. Press **Test** in Settings the first time you connect one.
- **The PPTX has never been opened in Microsoft PowerPoint itself.** Exports are
  verified by reading them back with python-pptx, shape by shape, and by
  rendering them in LibreOffice. Try one figure first on Windows.
- **Engine messages are English by default.** The interface is bilingual, but
  each engine message (for example "3 values are zero or negative and cannot be
  drawn on a log axis") needs a line in `web/notes.js` to appear in Chinese;
  without one it shows the English text.
- **Realistic illustration needs an image model.** Without one you get
  procedural placeholder shapes, marked as such on the figure.
- **A poster is typeset, not designed.** It guarantees that the content fits one
  sheet with consistent type and even columns. It will not have the visual idea
  for you.
- **The statistics are a tool, not a reviewer.** It warns about small samples,
  non-normal data and constant groups, but which test is appropriate, and
  whether the comparison is meaningful at all, is your call.

### Development

```bash
pip install -e ".[dev]"
python -m pytest -q          # 563 tests
```

One of them is worth calling out: `tests/test_parity.py` runs the JavaScript
renderer under node and diffs it against the Python renderer across seven scenes
and some twelve thousand formatted values. If the two ever disagree by one
decimal, CI goes red. It skips when node is not installed.

Pull requests welcome. If you touch rendering, keep the parity test green; if
you add an offline parsing rule, add the example that proves it, because that
part of the code is held up entirely by its examples.

---

MIT licensed. Not affiliated with, endorsed by, or derived from the code of any
commercial figure service.
