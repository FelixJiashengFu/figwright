"""Offline heuristics: useful figures with no model at all.

Everything here is plain text processing. It powers the built-in *offline demo*
provider, so the app works the moment it is installed (and so the test-suite
never needs a network). The results are deliberately modest: the heuristics
recognise explicit structure (arrows, numbered steps, "A activates B",
"duplicates 300") and do not pretend to understand prose.
"""

from __future__ import annotations

import math
import re
from typing import Any

from .builders.common import Canvas, has_cjk, pick_icon
from .themes import THEMES

KINDS = ("illustration", "flowchart", "workflow", "pathway", "abstract", "poster", "prisma")

_KIND_HINTS = [
    ("prisma", ("prisma", "系统综述", "系统评价", "文献筛选", "meta分析", "meta-analysis", "systematic review", "records screened")),
    ("poster", ("poster", "海报", "壁报")),
    ("abstract", ("graphical abstract", "图文摘要", "图形摘要", "toc graphic", "toc 图", "visual abstract")),
    ("pathway", ("pathway", "通路", "signaling", "signalling", "信号转导", "信号传导", "cascade", "级联", "-|", "⊣")),
    # Checked before "workflow": "实验流程图" and "a flow chart of the protocol"
    # both name the diagram explicitly, and that is what the person asked for.
    ("flowchart", ("flowchart", "flow chart", "流程图", "decision", "判断", "算法流程", "是否", "if ", "否则")),
    ("workflow", ("workflow", "实验流程", "技术路线", "protocol", "实验步骤", "pipeline", "研究路线", "操作步骤")),
]


def guess_lang(*texts: Any) -> str:
    return "zh" if has_cjk(*texts) else "en"


def guess_kind(prompt: str) -> str:
    """Pick the most plausible figure kind for a free-text request."""
    low = (prompt or "").lower()
    for kind, hints in _KIND_HINTS:
        if any(h in low for h in hints):
            return kind
    if re.search(r"(→|->|=>|➜)", low) or len(re.findall(r"(?m)^\s*(?:\d+[.)、]|[-*•])\s+", low)) >= 3:
        return "workflow"
    return "illustration"


# --------------------------------------------------------------------------- text
_FIGURE_WORDS = r"(?:图|流程|示意|摘要|海报|通路|路线|figure|diagram|flowchart|chart|workflow|pathway|abstract|poster|illustration|prisma)"
_INSTRUCTION = re.compile(
    r"^\s*(?:请|帮我|麻烦)?\s*(?:(?:画|绘制|生成|做|制作|设计|draw|create|make|generate|design|plot|show)[^:：\n]{0,40}?|[^:：\n，,。.;；]{0,12}?)"
    + _FIGURE_WORDS
    + r"[^:：\n，,。.;；]{0,24}[:：]\s*",
    re.I,
)
_LEAD = re.compile(
    r"^\s*(?:(?:step|步骤)\s*\d+\s*[:：.．、)]?|第[一二三四五六七八九十\d]+步\s*[:：，,]?|\(?\d{1,2}\s*[.．、)）]|[①-⑳]|[-*•·]\s+|"
    r"#{1,6}\s+|>\s+|"  # Markdown headings and quotes: source files arrive full of them.
    r"(?:first(?:ly)?|second(?:ly)?|third(?:ly)?|next|then|after that|afterwards|finally|lastly|and then|and)\b[,，]?|"
    r"首先|其次|然后|接着|随后|之后|最后|再次|先|再)\s*",
    re.I,
)
_STRONG = re.compile(r"\s*(?:→|->|=>|➜|⟶|⇒|\n|;|；|。|(?<=[a-z\)])\.\s+(?=[A-Z])|\bthen\b|然后|接着|随后|最后|[，,]\s*(?:再|并且?|同时)(?!次))\s*", re.I)
_WEAK = re.compile(r"\s*(?:,\s+|，|、)\s*")
_PAREN = re.compile(r"[（(][^（()）]*[)）]")
_HIDE = {",": "\x01", "，": "\x02", "、": "\x03", ";": "\x04", "；": "\x05", ".": "\x06", "。": "\x07"}
_SHOW = {v: k for k, v in _HIDE.items()}
_THEN_MARK = "\x0e"


def _mask(text: str) -> str:
    """Hide separators inside parentheses so "(3000 g, 10 min)" stays in one piece."""
    return _PAREN.sub(lambda m: "".join(_HIDE.get(ch, ch) for ch in m.group(0)), text)


def _unmask(text: str) -> str:
    return "".join(_SHOW.get(ch, ch) for ch in text)


def strip_instruction(prompt: str) -> str:
    """Drop a leading "draw a flowchart of:" style instruction."""
    return _INSTRUCTION.sub("", prompt or "", count=1).strip()


def _tidy(step: str) -> str:
    prev = None
    s = step.strip()
    while prev != s:
        prev = s
        s = _LEAD.sub("", s, count=1).strip()
    s = s.strip(" \t,，.。;；:：")
    return s[:1].upper() + s[1:] if s[:1].isascii() and s[:1].islower() and not re.match(r"^[a-z]{1,2}(?:[A-Z0-9]|-[A-Z])", s) else s


def split_steps(text: str, limit: int = 14) -> list[str]:
    """Split a description into ordered steps."""
    body = _mask(strip_instruction(text))
    # "if it passes then sequence" is one step: hide that "then" from the splitter.
    body = re.sub(r"(?i)(\b(?:if|when)\b[^\n.;→]{1,80}?[,\s])then\b", lambda m: m.group(1) + _THEN_MARK, body)
    # A numbered list written on one line: "1. sample 2. extract 3. sequence".
    if len(re.findall(r"(?<![\d.])\d{1,2}\s*[.．、)）]\s*\S", body)) >= 2:
        body = re.sub(r"\s*(?<![\d.])(\d{1,2})\s*[.．、)）]\s*", "\n", body)
    parts = [_tidy(p) for p in _STRONG.split(body)]
    parts = [p for p in parts if p]
    if len(parts) < 3:
        finer: list[str] = []
        for p in parts or [body]:
            finer += [_tidy(q) for q in _WEAK.split(p)]
        finer = [p for p in finer if p]
        if len(finer) > len(parts):
            parts = finer
    return [_unmask(p).replace(_THEN_MARK, "then") for p in parts[:limit]]


def title_detail(step: str, max_title: int = 26) -> tuple[str, str]:
    """Split "Centrifuge (3000 g, 10 min)" into a short title and a detail line."""
    m = re.match(r"^(.{1,60}?)\s*[（(]\s*(.+?)\s*[)）]\s*$", step)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = re.match(r"^(.{1,40}?)\s*(?:[:：]|\s[-–—]\s)\s*(.+)$", step)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    width = sum(2 if has_cjk(ch) else 1 for ch in step)
    if width > max_title * 2:
        m = re.match(r"^(.{4,40}?)[,，]\s*(.+)$", step)
        if m:
            return m.group(1).strip(), m.group(2).strip()
    return step, ""


def explicit_title(prompt: str) -> tuple[str, str]:
    """Return ``(title, rest)`` when the prompt carries a "title: ..." line."""
    m = re.search(r"(?im)^\s*(?:标题|题目|title)\s*[:：]\s*(.+?)\s*$", prompt or "")
    if not m:
        return "", prompt or ""
    return m.group(1).strip()[:160], (prompt[: m.start()] + prompt[m.end() :]).strip()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])\s*|(?<=[a-z0-9\)])\.\s+(?=[A-Z])|\n+", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def _short(s: str, limit: int) -> str:
    s = s.strip()
    width = 0
    for i, ch in enumerate(s):
        width += 2 if has_cjk(ch) else 1
        if width > limit:
            return s[: max(1, i - 1)].rstrip() + "…"
    return s


# --------------------------------------------------------------------- flowchart
_QUESTION = re.compile(r"[?？]\s*$|^(?:是否|if\b|whether\b|判断|检查是否|is\s|are\s|does\s|do\s|can\s)|是否|合格吗|通过吗", re.I)
_IO = re.compile(r"^(?:输入|输出|读取|读入|导入|导出|input|output|read|load|export|import|print)", re.I)
_DATA = re.compile(r"数据库|database|存储|保存到|store|save to", re.I)
_ELSE = re.compile(r"[,，;；]?\s*(?:否则|不然|若否|如果不是|otherwise|else|if not)[,，:：]?\s*(.+)$", re.I)
_ELSE_START = re.compile(r"^(?:否则|不然|若否|如果不是|如果不合格|不合格则?|otherwise|or else|else|if not)[,，:：]?\s*(?:则|就)?\s*(.+)$", re.I)
# "Is QC ok? If so, sequence" / "质检是否合格？如果合格则建库": the question, then what happens on "yes".
_THEN_Q = re.compile(
    r"^(.*?[?？])\s*(?:(?:如果|若是?|假如|要是|是的话|如是)[^，,则就]{0,12}?(?:[，,]\s*|则|就|那么)+"
    r"|(?:if\s+(?:yes|so|ok|true|it\s+\w+|passed)|yes)\s*[,:：]?\s*(?:then\s+)?)(.+)$",
    re.I,
)
_IF_THEN_ZH = re.compile(r"^(?:如果|若|假如|要是)\s*(.{1,30}?)\s*(?:的话)?\s*(?:[，,]\s*(?:则|就|那么)?|则|就|那么)\s*(.+)$")
# "合格的话就建库" — a condition with no "如果" in front of it.
_IF_THEN_DEHUA = re.compile(r"^(.{1,30}?)的话\s*[，,]?\s*(?:则|就|那么)?\s*(.+)$")
_IF_THEN_EN = re.compile(r"^(?:if|when|once)\s+(.{1,60}?)(?:[,:]\s*(?:then\s+)?|\s+then\s+)(.+)$", re.I)
# "when the sample passes go to library prep": no comma, but the verb says where
# the condition stops.
_IF_THEN_EN2 = re.compile(r"^(?:if|when|once)\s+(.{1,60}?)\s+(?:go to|go on to|proceed to|proceed with|continue to|continue with|move on to)\s+(.+)$", re.I)
_REDO = re.compile(r"重新|重做|重复|重试|返回|回到|再次|redo|repeat|retry|again|return to|go back|\bre-", re.I)


# "QC, if it passes, sequence" / "QC: when it passes, sequence" — the step and
# the condition arrived as one clause.
_INNER_IF = re.compile(r"^(.{2,40}?)\s*[，,;；:：]\s*((?:如果|若是?|假如|要是|if\s|when\s|once\s).+)$", re.I)


def _conditional(text: str) -> bool:
    return bool(_QUESTION.search(text) or _IF_THEN_ZH.match(text) or _IF_THEN_DEHUA.match(text) or _IF_THEN_EN.match(text) or _IF_THEN_EN2.match(text))


def _clauses(steps: list[str]) -> list[tuple[str, str]]:
    """Tag each step as a plain ``step``, the ``then`` branch or the ``else`` branch of a decision."""
    out: list[tuple[str, str]] = []
    queue = list(steps)
    while queue:
        step = queue.pop(0)
        m = _ELSE_START.match(step)
        if m and out:
            out.append(("else", _tidy(m.group(1))))
            continue
        # "QC, if it passes then sequence, otherwise re-extract": the action first, then its condition.
        m = _INNER_IF.match(step)
        if m and not _conditional(m.group(1)) and not _ELSE_START.match(m.group(1)):
            queue[:0] = [_tidy(m.group(1)), m.group(2).strip()]
            continue
        otherwise = None
        m = _ELSE.search(step)
        if m and _conditional(step[: m.start()] or step):
            otherwise = _tidy(m.group(1))
            step = step[: m.start()].strip()
        m = _THEN_Q.match(step)
        if m:
            out += [("step", m.group(1).strip()), ("then", _tidy(m.group(2)))]
        else:
            m = _IF_THEN_ZH.match(step) or _IF_THEN_DEHUA.match(step) or _IF_THEN_EN.match(step) or _IF_THEN_EN2.match(step)
            if m:
                cond = _tidy(m.group(1)).rstrip("?？")
                # "if it is NOT ok, redo": ask the positive question and put the action on the "no" branch.
                negative = re.match(r"^(?:不|未|没有?|非|unsuccessful|invalid)\s*(?=.)|^(?:not|no)\s+|\b(?:fails|failed|is\s+not|does\s*n[o']t)\b", cond, re.I)
                branch = "then"
                if negative and not any(r == "else" for r, _t in out[-2:]) and not _ELSE_START.match(queue[0] if queue else ""):
                    positive = cond[negative.end() :].strip() if negative.start() == 0 else (cond[: negative.start()] + " " + cond[negative.end() :]).strip()
                    if positive:
                        cond, branch = positive, "else"
                if re.fullmatch(r"[一-鿿]{1,3}", cond) and not cond.startswith(("是否", "能否", "有无")):
                    cond = "是否" + cond  # "如果合格则…" reads better as the question "是否合格？"
                question = cond + ("？" if has_cjk(step) else "?")
                out += [("step", question), (branch, _tidy(m.group(2)))]
            else:
                out.append(("step", step))
        if otherwise:
            out.append(("else", otherwise))
    return [(role, text) for role, text in out if text]


def flowchart_content(prompt: str) -> dict:
    title, rest = explicit_title(prompt)
    zh = guess_lang(prompt) == "zh"
    yes, no = ("是", "否") if zh else ("Yes", "No")
    items = _clauses(split_steps(rest))
    nodes: list[dict] = []
    edges: list[dict] = []

    def add(text: str, kind: str) -> str:
        nid = f"n{len(nodes) + 1}"
        nodes.append({"id": nid, "text": text, "kind": kind})
        return nid

    starts_itself = bool(items) and re.match(r"^(开始|start|begin)", items[0][1], re.I)
    prev = None if starts_itself else add("开始" if zh else "Start", "start")
    prev_label = ""
    last_process: str | None = None  # where a "no, do it again" loops back to
    decision: str | None = None  # the decision whose "no" branch has not been drawn yet
    loop_target: str | None = None
    dangling: list[str] = []  # side branches that rejoin the main line at the next step
    skipping: list[str] = []  # decisions whose "no" skips an optional step and lands on the next one
    last_step = max((i for i, (role, _t) in enumerate(items) if role == "step"), default=-1)
    for i, (role, step) in enumerate(items):
        if role == "else" and decision:
            alt = add(_short(step, 60), "process")
            edges.append({"from": decision, "to": alt, "label": no})
            if loop_target and _REDO.search(step):
                edges.append({"from": alt, "to": loop_target})  # "if not, redo X" loops back
            else:
                dangling.append(alt)
            decision = None
            continue
        if role == "then" and prev and nodes and nodes[-1]["id"] == prev and nodes[-1]["kind"] == "decision":
            nid = add(_short(step, 60), "process")
            edges.append({"from": prev, "to": nid, "label": yes})
            if loop_target and _REDO.search(step):
                edges.append({"from": nid, "to": loop_target})  # "if it failed, redo X": back up, do not go on
                prev = None
            else:
                prev = nid
            prev_label = ""
            continue
        if i == 0 and starts_itself:
            kind = "start"
        elif i == last_step and re.match(r"^(结束|end|finish|stop|done)", step, re.I):
            kind = "end"
        elif _QUESTION.search(step):
            kind = "decision"
            m = re.match(r"^(?:if|when|once|whether)\s+(.+?)[?.]?$", step, re.I)
            if m:
                step = m.group(1)[0].upper() + m.group(1)[1:] + "?"
        elif _IO.search(step):
            kind = "io"
        elif _DATA.search(step):
            kind = "data"
        else:
            kind = "process"
        nid = add(_short(step, 60), kind)
        if prev:
            edges.append({"from": prev, "to": nid, "label": prev_label})
        for d in dangling:
            edges.append({"from": d, "to": nid})
        for d in skipping:
            edges.append({"from": d, "to": nid, "label": no})
        dangling, skipping = [], []
        prev_label = ""
        if kind == "decision":
            decision, loop_target = nid, last_process
            has_then = i + 1 < len(items) and items[i + 1][0] == "then"
            if i + 1 < len(items) and items[i + 1][0] == "else":
                prev_label = yes  # the next clause is the "no" branch; the main line carries on as "yes"
            # "otherwise ..." may come right away or after the "yes" step.
            has_else = any(r == "else" for r, _t in items[i + 1 : i + 3])
            if not has_then:
                prev_label = yes
            if not has_else:
                if has_then:
                    skipping.append(nid)  # "if cloudy, filter": otherwise carry straight on
                elif last_process:
                    edges.append({"from": nid, "to": last_process, "label": no})  # a bare question: "no" means try again
                decision = None
        elif kind in ("process", "io", "data"):
            last_process = nid
        prev = nid
    if nodes and nodes[-1]["kind"] != "end":
        end = add("结束" if zh else "End", "end")
        if prev:
            edges.append({"from": prev, "to": end, "label": prev_label})
        for d in skipping:
            edges.append({"from": d, "to": end, "label": no})
        # Side branches that never rejoined finish at the end.
        targets = {e["from"] for e in edges}
        for n in nodes[:-1]:
            if n["id"] not in targets and n["kind"] != "end":
                edges.append({"from": n["id"], "to": end})
    return {"title": title, "direction": "TB", "nodes": nodes, "edges": edges}


# ----------------------------------------------------------------------- workflow
def workflow_content(prompt: str) -> dict:
    title, rest = explicit_title(prompt)
    steps = []
    for s in split_steps(rest, limit=12):
        t, d = title_detail(s)
        steps.append({"title": _short(t, 44), "detail": _short(d, 80)})
    return {"title": title, "steps": steps}


# ------------------------------------------------------------------------ pathway
_OUTCOMES = {
    "proliferation", "apoptosis", "survival", "growth", "differentiation", "migration", "inflammation", "autophagy", "transcription",
    "translation", "senescence", "angiogenesis", "metastasis", "degradation", "invasion", "necrosis", "pyroptosis", "ferroptosis",
    "cell cycle", "gene expression", "cell death", "protein synthesis", "glucose uptake", "immune response",
    "增殖", "凋亡", "存活", "生长", "分化", "迁移", "炎症", "自噬", "转录", "翻译", "衰老", "血管生成", "转移", "降解", "侵袭", "坏死", "焦亡", "铁死亡",
    "细胞周期", "基因表达", "细胞死亡", "蛋白合成", "葡萄糖摄取", "免疫应答", "细胞增殖", "细胞凋亡", "细胞存活", "细胞生长", "细胞分化", "细胞迁移",
}  # fmt: skip
_LIGANDS = {"egf", "tnf", "tnf-α", "tnfα", "il-6", "il-1β", "il-2", "il-10", "tgf-β", "tgfβ", "wnt", "insulin", "igf-1", "vegf", "ifn-γ", "ifnγ", "lps", "pdgf", "fgf", "hgf", "ngf", "bdnf", "胰岛素", "glucagon", "leptin", "epo"}
_RECEPTORS = {"tlr4", "tlr2", "cd4", "cd8", "pd-1", "pd-l1", "her2", "gpcr", "notch", "fzd", "lrp6", "insr", "tcr", "bcr", "rtk", "gp130", "trka", "trkb", "ctla-4"}
_KINASES = {
    "raf", "mek", "erk", "akt", "pi3k", "mtor", "mtorc1", "mtorc2", "jak", "jak1", "jak2", "src", "pka", "pkc", "ampk", "jnk", "p38", "ikk", "gsk3β", "gsk3",
    "cdk4", "cdk2", "pten", "pdk1", "lkb1", "atm", "atr", "chk1", "mapk", "ras", "rho", "rac1", "plc", "plcγ", "tak1", "irak4", "caspase-3", "caspase-9", "mst1", "lats1",
}  # fmt: skip
_TFS = {"stat3", "stat1", "stat5", "nf-κb", "nfκb", "nfkb", "nf-kb", "myc", "c-myc", "p53", "tp53", "creb", "foxo", "foxo3", "smad", "smad2", "smad3", "smad2/3", "hif-1α", "hif1a", "β-catenin", "tcf", "ap-1", "c-fos", "c-jun", "nrf2", "e2f", "yap", "taz", "srebp", "irf3", "gli1", "elk1"}
_MOLECULES = {"camp", "ca2+", "ip3", "dag", "pip3", "pip2", "atp", "adp", "ros", "no", "gtp", "gdp", "cgmp", "nad+", "nadh"}
_STOP = {
    "the", "this", "that", "these", "then", "when", "after", "upon", "which", "it", "in", "on", "at", "as", "and", "but", "finally", "subsequently", "activated",
    "once", "here", "we", "they", "both", "next", "first", "second", "third", "thus", "therefore", "meanwhile", "however", "phosphorylated", "active", "binding",
    "activation", "inhibition", "signal", "signaling", "signalling", "pathway", "figure", "draw", "create", "show", "please", "a", "an", "of", "to", "with", "by",
    "for", "from", "into", "is", "are", "its", "their", "title", "i", "make", "generate", "diagram", "where", "while", "also", "in turn", "turn",
}  # fmt: skip

_CJK_FILLERS = ("然后", "之后", "随后", "接着", "从而", "进而", "继而", "最终", "最后", "进一步", "并且", "同时", "可以", "能够", "直接", "间接", "可", "会", "被", "再", "又", "并", "也", "后", "和", "与", "的", "能", "则", "而")
_PLACES = {"细胞核", "胞核", "核内", "细胞质", "胞质", "胞浆", "细胞膜", "胞膜", "线粒体", "内质网", "细胞外", "胞外", "细胞内", "胞内", "细胞"}
_DRUGS = {"aspirin", "metformin", "rapamycin", "dexamethasone", "cisplatin", "paclitaxel", "doxorubicin", "tamoxifen", "ibuprofen", "insulin glargine", "warfarin", "heparin", "morphine", "caffeine", "nicotine"}
_DRUG_SUFFIX = r"(nib|mab|statin|mycin|formin|olimus|parib|ciclib|sone|platin|taxel|rubicin|oxifen|profen|prazole|sartan|pril|olol|dipine|cillin|floxacin|inhibitor|antagonist|blocker|drug)$"
_NAME_LATIN = r"[A-Za-zα-ωΑ-Ω][A-Za-z0-9α-ωΑ-Ω+]*(?:[-/][A-Za-z0-9α-ωΑ-Ω+]+)*"
# A role word belongs to the name in front of it: "MEK inhibitor" and "IL-6
# receptor" are one entity each, not a name followed by a word to throw away.
_ROLE_WORD = r"inhibitors?|antagonists?|agonists?|blockers?|activators?|receptors?|ligands?|kinases?|antibod(?:y|ies)|complex(?:es)?"
_NAME_PHRASE = rf"{_NAME_LATIN}(?:[ \t]+(?:{_ROLE_WORD})\b)?"  # spaces only: a line break ends the sentence
_NAME_CJK = r"[一-鿿]{1,6}(?:受体|蛋白|激酶|因子|素|酶|通道|复合物)"
_VERBS = [
    ("inhibit", r"-\||⊣|--\||inhibits?|represses?|suppress(?:es)?|blocks?|downregulates?|degrades?|antagoni[sz]es?|抑制|阻断|下调|降解|拮抗|阻止"),
    ("translocate", r"translocates?\s+(?:to|into)(?:\s+the)?|enters?(?:\s+the)?|转位(?:到|至|进入)?|入核|进入"),
    ("bind", r"binds?(?:\s+to)?|interacts?\s+with|associates?\s+with|结合(?:到|于)?|相互作用"),
    ("activate", r"->|→|=>|⟶|activates?|stimulates?|phosphorylates?|induces?|promotes?|recruits?|upregulates?|triggers?|drives?|leads?\s+to|激活|磷酸化|促进|诱导|招募|上调|触发|导致|引起"),
]


def guess_entity_type(name: str) -> str:
    low = name.lower()
    if low in _OUTCOMES:
        return "process"
    if low in _MOLECULES:
        return "molecule"
    if low in _TFS:
        return "tf"
    if low in _DRUGS or re.search(_DRUG_SUFFIX, low) or re.search(r"药|抑制剂|拮抗剂|阻断剂|(?:抗体|替尼|单抗|他汀|霉素|米松|双胍|西林|沙星|洛尔|地平|普利|沙坦|拉唑|紫杉醇|铂|司匹林)$", name):
        return "drug"
    if low in _KINASES or low.endswith("kinase") or name.endswith(("激酶", "酶")):
        return "kinase"
    if low in _LIGANDS or name.endswith(("因子", "素")) or low.endswith("factor"):
        return "ligand"
    if low in _RECEPTORS or low.endswith("receptor") or name.endswith(("受体", "通道")) or re.fullmatch(r"[A-Z][A-Z0-9]{1,5}R\d?", name):
        return "receptor"
    if "/" in name or name.endswith("复合物"):
        return "complex"
    if re.match(r"^(?:mir|let|lnc|circ|pre-mir|mi)[-\s]?\w", low) or low.endswith(("rna", "mrna", "mirna", "lncrna", "sirna")) or name.endswith(("核酸", "转录本")):
        return "rna"
    if name.endswith(("细胞核", "细胞膜", "细胞质", "线粒体", "内质网", "高尔基体", "溶酶体", "核膜", "胞外", "胞内")) or low in ("nucleus", "cytoplasm", "membrane", "mitochondria", "mitochondrion", "er", "golgi", "lysosome", "extracellular"):
        return "compartment"
    if re.fullmatch(r"[A-Z][A-Z0-9-]{1,9}", name) and name.isupper() and name.endswith(("GENE",)):
        return "gene"
    return "protein"


def _trim_article(tok: str) -> str:
    """"the EGF receptor" names the same thing as "EGF receptor"."""
    first, _, rest = tok.partition(" ")
    return rest if rest and first.lower() in _STOP else tok


def _is_name(tok: str, sentence_start: bool) -> bool:
    low = tok.lower()
    if " " in tok:  # a name plus its role word; the role word alone is judged below
        return _is_name(tok.split(" ")[0], sentence_start) or bool(re.search(_DRUG_SUFFIX, low)) or low.split()[-1].rstrip("s") in ("receptor", "kinase", "ligand", "complex", "antibody")
    if low in _OUTCOMES or low in _LIGANDS or low in _KINASES or low in _TFS or low in _MOLECULES or low in _RECEPTORS:
        return True
    if low in _STOP or len(tok) < 2:
        return False
    if has_cjk(tok):
        return True
    if any(ch.isdigit() for ch in tok) or any(ch.isupper() for ch in tok[1:]) or any(ch in "αβγδκ" for ch in tok):
        return True
    if tok[0].isupper() and not sentence_start:
        return True
    return tok[0].isupper() and bool(re.search(r"(in|ib|ab|one|ol|ide|ase)$", low))


def pathway_content(prompt: str) -> dict:
    title, rest = explicit_title(prompt)
    text = strip_instruction(rest)
    outcomes = sorted(_OUTCOMES, key=len, reverse=True)
    verb_alt = "|".join(f"(?P<v{i}>{pat})" for i, (_t, pat) in enumerate(_VERBS))
    outcome_alt = "|".join(re.escape(o) for o in outcomes)
    verb_only = "|".join(pat for _t, pat in _VERBS)
    # A plain Chinese word counts as a name only next to a verb ("药物 抑制 MEK"), see below.
    word = rf"(?P<word>[一-鿿]{{1,8}}?(?=(?:{verb_only})|[^一-鿿]|$))"
    token = re.compile(rf"{verb_alt}|(?P<name>{outcome_alt}|{_NAME_CJK}|{_NAME_PHRASE})|{word}|(?P<stop>[.。;；\n])", re.I)
    verb_next = re.compile(rf"\s*(?:{verb_only})", re.I)

    order: list[str] = []
    display: dict[str, str] = {}
    relations: list[dict] = []
    seen: set[tuple[str, str]] = set()
    prev: str | None = None
    pending: str | None = None
    sentence_start = True
    for m in token.finditer(text):
        if m.group("stop"):
            sentence_start = True
            pending = None
            continue
        verb = next((_VERBS[i][0] for i in range(len(_VERBS)) if m.group(f"v{i}")), None)
        if verb:
            pending = verb
            sentence_start = False
            continue
        tok = m.group("name")
        if tok is None:
            tok = m.group("word")
            for filler in _CJK_FILLERS:
                if tok.endswith(filler):
                    tok = tok[: -len(filler)]
                if tok.startswith(filler):
                    tok = tok[len(filler) :]
            if tok in _PLACES:
                continue  # "ERK 进入细胞核激活 MYC": the compartment is where, not who
            ok = len(tok) >= 2 and tok not in _CJK_FILLERS and (pending is not None or bool(verb_next.match(text, m.end())))
        else:
            tok = _trim_article(tok)
            ok = _is_name(tok, sentence_start)
        sentence_start = False
        if not ok:
            continue
        key = tok.lower()
        if key not in display:
            display[key] = tok
            order.append(key)
        if pending and prev and prev != key and (prev, key) not in seen:
            seen.add((prev, key))
            relations.append({"from": prev, "to": key, "type": pending})
        pending = None
        prev = key

    if not relations:
        steps = split_steps(rest, limit=10)
        order = [f"s{i}" for i in range(len(steps))]
        display = {f"s{i}": _short(s, 36) for i, s in enumerate(steps)}
        relations = [{"from": a, "to": b, "type": "activate"} for a, b in zip(order, order[1:])]
    entities = [{"id": k, "name": display[k], "type": guess_entity_type(display[k])} for k in order]
    targets = {r["to"] for r in relations}
    for ent in entities:
        out = [r["type"] for r in relations if r["from"] == ent["id"]]
        if ent["type"] == "protein" and ent["id"] not in targets and out and all(t == "inhibit" for t in out):
            ent["type"] = "drug"  # something that only ever blocks others and has no upstream: an added inhibitor
    return {"title": title, "entities": entities, "relations": relations}


# ----------------------------------------------------------------------- abstract
_SECTION_WORDS = {
    "background": ("background", "introduction", "motivation", "problem", "背景", "引言", "问题", "研究背景", "动机"),
    "methods": ("methods", "method", "approach", "design", "materials and methods", "方法", "设计", "研究方法", "材料与方法", "思路"),
    "results": ("results", "result", "findings", "结果", "发现", "研究结果"),
    "conclusion": ("conclusion", "conclusions", "takeaway", "significance", "summary", "结论", "意义", "总结", "展望"),
}


def _labelled_parts(text: str) -> dict[str, str]:
    words = [w for ws in _SECTION_WORDS.values() for w in ws]
    pattern = re.compile(r"(?im)(?:^|(?<=[\s。.;；]))\s*[#*【\[]*\s*(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\s*[】\]*]*\s*[:：]\s*")
    hits = list(pattern.finditer(text))
    out: dict[str, str] = {}
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        word = m.group(1).lower()
        key = next(k for k, ws in _SECTION_WORDS.items() if word in ws)
        out.setdefault(key, text[m.end() : end].strip())
    return out


def abstract_content(prompt: str) -> dict:
    title, rest = explicit_title(prompt)
    text = strip_instruction(rest)
    zh = guess_lang(prompt) == "zh"
    heads = {"background": "背景", "methods": "方法", "results": "结果"} if zh else {"background": "Background", "methods": "Approach", "results": "Findings"}
    parts = _labelled_parts(text)
    panels: list[dict] = []
    takeaway = ""
    if len(parts) >= 2:
        for key in ("background", "methods", "results"):
            if parts.get(key):
                panels.append({"heading": heads[key], "bullets": [_short(s, 96) for s in sentences(parts[key])[:3]]})
        takeaway = _short(parts.get("conclusion", ""), 220)
    else:
        sents = sentences(text)
        if len(sents) < 3:
            sents = split_steps(text, limit=9) or sents
        if len(sents) >= 4:
            takeaway = _short(sents.pop(), 220)
        n = len(sents)
        if n <= 3:
            for s in sents:
                t, d = title_detail(s)
                panels.append({"heading": _short(t, 30), "bullets": [_short(d, 96)] if d else []})
        else:
            a, b = math.ceil(n / 3), math.ceil(2 * n / 3)
            for key, chunk in (("background", sents[:a]), ("methods", sents[a:b]), ("results", sents[b:])):
                if chunk:
                    panels.append({"heading": heads[key], "bullets": [_short(s, 96) for s in chunk[:3]]})
    return {"title": title, "panels": panels, "takeaway": takeaway}


# ------------------------------------------------------------------------- poster
_POSTER_HEADS = (
    "abstract", "introduction", "background", "objective", "objectives", "aims", "methods", "materials and methods", "methodology", "results", "discussion",
    "conclusion", "conclusions", "references", "acknowledgements", "acknowledgments", "future work", "limitations",
    "摘要", "引言", "背景", "研究背景", "目的", "研究目的", "方法", "研究方法", "材料与方法", "结果", "研究结果", "讨论", "结论", "参考文献", "致谢", "展望", "局限性",
)  # fmt: skip


def poster_content(prompt: str, source: str = "") -> dict:
    title, rest = explicit_title(prompt)
    text = (source or "").strip() or strip_instruction(rest)
    zh = guess_lang(text) == "zh"
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    head_re = re.compile(r"^\s*(?:#{1,4}\s*)?(?:\d+[.、]?\s*)?(" + "|".join(re.escape(h) for h in sorted(_POSTER_HEADS, key=len, reverse=True)) + r")\s*[:：]?\s*(.*)$", re.I)
    md_re = re.compile(r"^\s*#{1,4}\s+(.+?)\s*$")
    sections: list[dict] = []
    preamble: list[str] = []
    for ln in lines:
        m = head_re.match(ln)
        md = md_re.match(ln)
        if m and len(m.group(2)) < 400 and (not m.group(2) or ln.lstrip().startswith("#") or re.search(r"[:：]", ln[: len(m.group(1)) + 6])):
            sections.append({"heading": m.group(1).strip().capitalize() if not zh else m.group(1).strip(), "body": m.group(2).strip()})
        elif md and sections:
            sections.append({"heading": md.group(1), "body": ""})
        elif md and not sections and not title:
            title = md.group(1)
        elif sections:
            sections[-1]["body"] = (sections[-1]["body"] + "\n" + ln).strip() if ln.strip() else sections[-1]["body"]
        elif ln.strip():
            preamble.append(ln.strip())
    authors = affiliations = ""
    if preamble and not title and len(preamble[0]) <= 160 and (len(preamble) > 1 or not re.search(r"[。.；;！!?？]", preamble[0])):
        # One paragraph of prose and nothing else is what the poster is about,
        # so it becomes the body; a short headline with no full stop is a title.
        title = preamble.pop(0)
    if sections and preamble:
        authors = preamble.pop(0)
        if preamble:
            affiliations = preamble.pop(0)
    if not sections:
        paras = [p.strip() for p in re.split(r"\n\s*\n", "\n".join(preamble)) if p.strip()]
        if len(paras) < 3:
            sents = sentences(" ".join(preamble))
            k = max(1, math.ceil(len(sents) / 4))
            paras = [" ".join(sents[i : i + k]) for i in range(0, len(sents), k)]
        names = ["背景", "方法", "结果", "结论", "补充"] if zh else ["Background", "Methods", "Results", "Conclusions", "Notes"]
        sections = [{"heading": names[min(i, len(names) - 1)], "body": p} for i, p in enumerate(paras[:6])]
    for s in sections:
        s["body"] = s["body"][:1800]
        if re.match(r"^(results?|结果|研究结果)$", s["heading"], re.I):
            s["figure"] = True
    return {"title": title or ("未命名海报" if zh else "Untitled poster"), "authors": authors[:300], "affiliations": affiliations[:300], "sections": sections[:9]}


# ------------------------------------------------------------------------- prisma
_PRISMA_KEYS = [
    ("databases", r"databases?|数据库"),
    ("registers", r"registers?|registries|注册库|注册平台|登记"),
    # How many were found in the first place. Checked before the words below so
    # that "1200 records identified" is not read as a count of duplicates.
    ("identified_total", r"records? identified|identified|检索到|共检索|检索获得|检出|初步检索|初检"),
    # "900 after duplicates removed" is what is LEFT, not how many were removed.
    ("after_duplicates", r"去重后|查重后|除重后|剩余|after (?:removing )?duplicates?|after duplicates? (?:were |are )?removed"),
    ("duplicates", r"duplicates? records? removed|duplicates? removed|removed as duplicates?|去重(?!后)|重复记录|重复"),
    ("automation", r"automation|自动化"),
    ("other_removed", r"other reasons|其他原因"),
    ("not_retrieved", r"not retrieved|未获取|未能获取|无法获取|未获得全文"),
    ("sought", r"sought|retrieval|尝试获取|获取全文"),
    ("assessed", r"assessed|eligibility|全文评估|评估"),
    ("screened", r"screened|筛选(?!排除)|初筛(?!排除)"),
    ("excluded", r"records excluded|excluded (?:by|at|during|in) (?:title|abstract|screening|the title)|screened out|title and abstract|题目和摘要|筛选排除|初筛排除|标题摘要|排除"),
    ("excluded_reports_total", r"(?:reports?|full[- ]texts?|articles?) excluded|excluded (?:after|at|during|on) full[- ]text|全文排除|全文后排除|复筛排除"),
    ("included_studies", r"included|纳入"),
]
_NUM = r"(\d[\d,，]*)"


def prisma_content(prompt: str) -> dict:
    title, rest = explicit_title(prompt)
    text = strip_instruction(rest)
    # The boxes are standard wording, so they follow the language asked in, even
    # when every number arrives as a bare digit.
    out: dict[str, Any] = {"title": title, "lang": guess_lang(prompt)}
    taken: list[tuple[int, int]] = []
    for key, pat in _PRISMA_KEYS:
        for rx in (rf"(?:{pat})[^\d\n。.;；,，]{{0,24}}?{_NUM}", rf"{_NUM}[^\d\n。.;；,，]{{0,14}}?(?:{pat})"):
            found = None
            for m in re.finditer(rx, text, re.I):
                span = m.span(1)
                if any(a < span[1] and span[0] < b for a, b in taken):
                    continue
                found = m
                break
            if found:
                out[key] = int(re.sub(r"[,，]", "", found.group(1)))
                taken.append(found.span(1))
                break
    # "full-text excluded 180 (wrong population 100, no control 60)"
    m = re.search(r"(?:reports? excluded|full[- ]text[^\d\n]{0,20}excluded|全文排除|全文阅读后排除|复筛排除)[^\d\n(（]{0,16}" + _NUM + r"?[^\n(（]{0,10}[(（]([^)）]+)[)）]", text, re.I)
    if m:
        reasons = []
        for part in re.split(r"[,，;；、]", m.group(2)):
            mm = re.match(r"^\s*(.+?)\s*[:：=]?\s*(?:n\s*=\s*)?(\d[\d,]*)\s*(?:篇|条|项)?\s*$", part)
            if mm and mm.group(1).strip().lower() not in ("", "n", "共", "总计", "合计", "total"):
                reasons.append({"reason": mm.group(1).strip(), "n": int(mm.group(2).replace(",", ""))})
        if reasons:
            out["excluded_reports"] = reasons
        elif m.group(1):
            out["excluded_reports_total"] = int(re.sub(r"[,，]", "", m.group(1)))
    left = out.pop("after_duplicates", None)
    if left is not None:
        # The number left after de-duplication is PRISMA's "records screened"
        # box; the removed count is the difference, if we know what came in.
        out.setdefault("screened", left)
        total = out.get("identified_total")
        if total is not None and total >= left:
            out["duplicates"] = total - left
        elif out.get("duplicates") is not None and out["duplicates"] >= left:
            out.pop("duplicates")
    return out


# ------------------------------------------------------------------- illustration
def concept_map(prompt: str, theme: str | None = None) -> dict:
    """Free-form fallback: a hub-and-spoke concept map built from key phrases."""
    title, rest = explicit_title(prompt)
    steps = split_steps(rest, limit=9)
    if len(steps) < 2:
        steps = [s for s in sentences(strip_instruction(rest))][:9] or [strip_instruction(rest) or "?"]
    hub_text = title
    if not hub_text:
        hub_text, _d = title_detail(steps[0])
        if len(steps) > 3:
            steps = steps[1:]
    c = Canvas(theme, "illustration", title)
    W, H = 1100.0, 760.0
    cx, cy = W / 2, H / 2 + (16 if title else 0)
    n = len(steps)
    hub = c.add("ellipse", cx - 120, cy - 60, 240, 120, id="hub", text=_short(hub_text, 46), fill=c.soft(0), stroke=c.strong(0), fontWeight="bold", fontSize=18)
    rx, ry = 400.0, 262.0
    for i, step in enumerate(steps):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        px, py = cx + rx * math.cos(ang), cy + ry * math.sin(ang)
        t, d = title_detail(step)
        nid = c.add("icon", px - 85, py - 62, 170, 124, id=f"k{i + 1}", icon=pick_icon(None, step, default="lightbulb"), text=_short(t, 34), fill=c.soft(i + 1), accent=c.strong(i + 1), fontSize=14)
        c.edge(hub, nid, head="none", color=c.muted)
    if title:
        c.title(title, W)
    return c.finish(W, H + (30 if title else 0))


def _structure_found(content: dict) -> int:
    """How much structure a parse actually found, so two parses can be compared."""
    if content.get("relations") is not None:
        return len(content.get("relations") or [])
    items = content.get("nodes") or content.get("steps") or []
    return len([i for i in items if not isinstance(i, dict) or i.get("kind") not in ("start", "end")])


def content_for(kind: str, prompt: str, source: str = "") -> dict:
    """Semantic content for a structured figure kind, derived without a model."""
    if kind == "abstract":
        return abstract_content(prompt if not source else f"{prompt}\n{source}")
    if kind == "poster":
        return poster_content(prompt, source)
    if kind == "prisma":
        return prisma_content(prompt if not source else f"{prompt}\n{source}")
    build = {"flowchart": flowchart_content, "workflow": workflow_content, "pathway": pathway_content}.get(kind)
    if build is None:
        raise ValueError(f"No offline builder for {kind!r}.")
    out = build(prompt)
    # "Draw the methods as a flowchart" is an instruction, not content. When a
    # document came with the request, the steps are in the document, not the ask.
    if (source or "").strip() and _structure_found(out) < 2:
        from_source = build(source)
        if _structure_found(from_source) > _structure_found(out):
            return from_source
    return out


# -------------------------------------------------------------------------- refine
_COLOURS = {
    "红": "#e53935", "蓝": "#2f6fb7", "绿": "#2e9e59", "黄": "#f2c230", "橙": "#f08c2e", "紫": "#8a5fc7", "粉": "#e87aa4", "灰": "#8a8f98", "黑": "#000000",
    "白": "#ffffff", "青": "#2a9d8f", "棕": "#8d5a3b", "red": "#e53935", "blue": "#2f6fb7", "green": "#2e9e59", "yellow": "#f2c230", "orange": "#f08c2e",
    "purple": "#8a5fc7", "pink": "#e87aa4", "gray": "#8a8f98", "grey": "#8a8f98", "black": "#000000", "white": "#ffffff", "teal": "#2a9d8f", "brown": "#8d5a3b",
}  # fmt: skip
_THEME_WORDS = {"墨蓝": "ink", "珊瑚": "coral", "森林": "forest", "极简": "mono", "灰度": "mono", "黑白": "mono", "色盲": "okabe", "colour-blind": "okabe", "color-blind": "okabe", "colorblind": "okabe"}


def _colour(word: str) -> str | None:
    w = word.strip().lower().rstrip("色的 ")
    if re.fullmatch(r"#[0-9a-f]{3}(?:[0-9a-f]{3})?", w):
        return w
    return _COLOURS.get(w)


def _match_nodes(scene: dict, needle: str) -> list[dict]:
    needle = needle.strip().strip("\"'“”‘’「」")
    if not needle:
        return []
    exact = [n for n in scene.get("nodes", []) if n["id"] == needle or (n.get("text") or "").strip().lower() == needle.lower()]
    if exact:
        return exact
    return [n for n in scene.get("nodes", []) if needle.lower() in (n.get("text") or "").lower()]


def refine_ops(scene: dict, instruction: str) -> list[dict]:
    """Translate a simple edit request into operations (see :mod:`figwright.ops`)."""
    text = (instruction or "").strip()
    low = text.lower()
    ops: list[dict] = []
    style = scene.get("style") or {}

    for word, theme in list(_THEME_WORDS.items()) + [(t, t) for t in THEMES]:
        if word in low and re.search(r"主题|配色|theme|palette|色盲|colou?r", low):
            if style.get("theme") != theme:
                ops.append({"op": "set_theme", "theme": theme})
            break

    m = re.search(r"(?:字号|字体大小|font\s*size)\s*(?:改为|改成|设为|调到|to|=|:|：)?\s*(\d{1,3})", low)
    fs = float(style.get("fontSize", 16))
    if m:
        ops.append({"op": "set_style", "set": {"fontSize": int(m.group(1))}})
    elif re.search(r"字[体号]?.{0,4}(大|加大|放大)|(bigger|larger)\s+(text|font)|(text|font)\s+(bigger|larger)|increase.{0,10}font", low):
        ops.append({"op": "set_style", "set": {"fontSize": round(fs * 1.15, 1)}})
    elif re.search(r"字[体号]?.{0,4}(小|缩小)|smaller\s+(text|font)|(text|font)\s+smaller|decrease.{0,10}font", low):
        ops.append({"op": "set_style", "set": {"fontSize": round(fs / 1.15, 1)}})

    if re.search(r"线.{0,4}(粗|加粗)|thicker", low):
        ops.append({"op": "set_style", "set": {"strokeWidth": float(style.get("strokeWidth", 2)) + 0.75, "edgeWidth": float(style.get("edgeWidth", 2)) + 0.75}})
    elif re.search(r"线.{0,4}细|thinner", low):
        ops.append({"op": "set_style", "set": {"strokeWidth": max(0.75, float(style.get("strokeWidth", 2)) - 0.75), "edgeWidth": max(0.75, float(style.get("edgeWidth", 2)) - 0.75)}})

    m = re.search(r"(?:标题|题目)\s*(?:改为|改成|换成|设为|叫|是|[:：])\s*[\"“「]?(.+?)[\"”」]?\s*$", text) or re.search(r"(?i)\btitle\s*(?:to|as|:|=)\s*[\"“]?(.+?)[\"”]?\s*$", text)
    if m:
        ops.append({"op": "set_title", "title": m.group(1).strip()})

    m = re.search(r"背景.{0,3}(?:改为|改成|换成|设为|用)?\s*([#\w一-鿿]+?)色?\s*$", text) or re.search(r"(?i)background\s*(?:to|:|=|colou?r)?\s*([#\w]+)\s*$", text)
    if m and _colour(m.group(1)):
        ops.append({"op": "set_canvas", "background": _colour(m.group(1))})

    m = re.search(r"把\s*[\"“「]?(.+?)[\"”」]?\s*(?:改为|改成|换成|替换为|替换成|变成)\s*[\"“「]?(.+?)[\"”」]?\s*$", text) or re.search(
        r"(?i)\b(?:rename|replace|change|make)\s+[\"“]?(.+?)[\"”]?\s+(?:to|with|into)\s+[\"“]?(.+?)[\"”]?\s*$", text
    ) or re.search(r"(?i)\bmake\s+[\"“]?(.+?)[\"”]?\s+(red|blue|green|yellow|orange|purple|pink|gr[ae]y|black|white|teal|brown)\s*$", text)
    if m and not re.match(r"^(标题|题目|背景|the title|title|the background|background)$", m.group(1).strip(), re.I):
        a, b = m.group(1).strip(), m.group(2).strip()
        colour = _colour(b)
        if colour:
            for n in _match_nodes(scene, a):
                ops.append({"op": "update", "id": n["id"], "set": {"fill": colour}})
        else:
            ops.append({"op": "replace_text", "find": a, "replace": b})

    m = re.search(r"(?:删除|删掉|去掉|移除)\s*[\"“「]?(.+?)[\"”」]?\s*$", text) or re.search(r"(?i)\b(?:delete|remove)\s+(?:the\s+)?[\"“]?(.+?)[\"”]?\s*$", text)
    if m:
        hits = _match_nodes(scene, re.sub(r"(这个|节点|方框|步骤| node| box| step)$", "", m.group(1).strip()))
        if hits:
            ops.append({"op": "delete", "ids": [n["id"] for n in hits]})

    m = re.search(r"(?:连接|连线)\s*[\"“「]?(.+?)[\"”」]?\s*(?:和|与|到|->|→)\s*[\"“「]?(.+?)[\"”」]?\s*$", text) or re.search(r"(?i)\bconnect\s+[\"“]?(.+?)[\"”]?\s+(?:to|and|with)\s+[\"“]?(.+?)[\"”]?\s*$", text)
    if m:
        a, b = _match_nodes(scene, m.group(1)), _match_nodes(scene, m.group(2))
        if a and b and a[0]["id"] != b[0]["id"]:
            ops.append({"op": "add_edge", "edge": {"from": a[0]["id"], "to": b[0]["id"]}})

    m = re.search(r"(?:添加|增加|加一个|加上|新增)(?:一个)?(?:节点|方框|步骤|文字|标注)?\s*[:：]?\s*[\"“「]?(.+?)[\"”」]?\s*$", text) or re.search(r"(?i)\badd\s+(?:a\s+|an\s+)?(?:new\s+)?(?:node|box|step|label|text)\s*(?:called|named|:)?\s*[\"“]?(.+?)[\"”]?\s*$", text)
    if m and not any(o["op"] == "add_edge" for o in ops):
        label = m.group(1).strip()
        nodes = [n for n in scene.get("nodes", []) if not n.get("hidden")]
        y = max((n["y"] + n["h"] for n in nodes), default=40.0) + 30
        x = min((n["x"] for n in nodes), default=40.0)
        ops.append({"op": "add_node", "node": {"type": "rect", "text": label, "x": x, "y": y}})
        ops.append({"op": "set_canvas", "height": max(float(scene.get("height", 800)), y + 110)})
    return ops


REFINE_HELP = {
    "zh": "离线演示模式只认识这些修改：换主题（如“换成森林主题”）、字体大一点/小一点、字号 18、线条粗一点、标题改为 X、把 A 改成 B、把 A 改成红色、删除 A、连接 A 和 B、添加节点 X、背景改为白色。接入大模型后可以随便说。",
    "en": "Offline demo mode understands: switch theme (e.g. 'use the forest theme'), bigger/smaller text, font size 18, thicker lines, title to X, rename A to B, make A red, delete A, connect A to B, add node X, background white. Connect a model for free-form requests.",
}


# ---------------------------------------------------------------------------- plot
_PLOT_WORDS = [
    ("volcano", ("volcano", "火山")),
    ("heatmap", ("heatmap", "heat map", "热图", "相关矩阵", "correlation matrix")),
    ("violin", ("violin", "小提琴")),
    ("box", ("box", "箱线", "箱形", "箱型")),
    ("hist", ("hist", "直方", "distribution", "分布")),
    ("scatter", ("scatter", "散点", "correlat", "相关", "regress", "回归")),
    ("line", ("line", "折线", "trend", "趋势", "time course", "time series", "随时间", "曲线")),
    ("pie", ("pie", "饼", "donut", "环形")),
    ("bar", ("bar", "柱", "条形", "column")),
]


def plot_spec(prompt: str, columns: list[dict]) -> dict:
    """Choose a chart for a table. ``columns`` is ``[{"name", "type", "unique"}]``."""
    low = (prompt or "").lower()
    kind = next((k for k, words in _PLOT_WORDS if any(w in low for w in words)), None)
    numeric = [c["name"] for c in columns if c.get("type") == "number"]
    categorical = [c["name"] for c in columns if c.get("type") != "number"]
    # A numeric column holding one repeated value is a label ("dose = 1 everywhere"),
    # not the thing measured, so it is the last choice when nothing was named.
    uniq = {c["name"]: int(c.get("unique") or 0) for c in columns}
    measured = sorted(numeric, key=lambda n: -uniq.get(n, 0))
    varying = [c for c in measured if uniq.get(c, 0) > 1] or measured
    mentioned = sorted((c["name"] for c in columns if c["name"] and c["name"].lower() in low), key=lambda name: low.find(name.lower()))
    spec: dict[str, Any] = {"title": explicit_title(prompt)[0]}
    lowmap = {c["name"].lower(): c["name"] for c in columns}

    if kind == "volcano" or ({"log2fc", "log2foldchange", "logfc"} & set(lowmap) and {"pvalue", "padj", "p", "p_value", "fdr", "p.value", "p.adj"} & set(lowmap) and kind is None):
        fc = next((lowmap[k] for k in ("log2fc", "log2foldchange", "logfc") if k in lowmap), numeric[0] if numeric else None)
        pv = next((lowmap[k] for k in ("padj", "p.adj", "fdr", "pvalue", "p_value", "p.value", "p") if k in lowmap), numeric[1] if len(numeric) > 1 else None)
        spec.update(kind="volcano", x=fc, y=[pv] if pv else [], label=categorical[0] if categorical else None)
        return spec

    if kind is None:
        if categorical and numeric:
            first = next((c for c in columns if c["name"] == categorical[0]), {})
            repeated = first.get("unique", 0) and first.get("rows", 0) and first["unique"] < first["rows"]
            kind = "box" if repeated else "bar"
        elif len(numeric) >= 2:
            kind = "scatter"
        elif numeric:
            kind = "hist"
        else:
            kind = "bar"
    spec["kind"] = kind
    m_num = [c for c in mentioned if c in numeric]
    m_cat = [c for c in mentioned if c in categorical]
    if kind in ("bar", "box", "violin", "pie"):
        spec["x"] = (m_cat or categorical or [columns[0]["name"]] if columns else [None])[0]
        ys = m_num or [c for c in varying if c != spec["x"]]
        spec["y"] = ys[:1] if kind in ("pie", "box", "violin") else ys[:6]
    elif kind == "line":
        spec["x"] = (m_num[:1] or [columns[0]["name"]] if columns else [None])[0] if not m_cat else m_cat[0]
        if not m_cat and columns:
            spec["x"] = columns[0]["name"]
        spec["y"] = [c for c in (m_num or varying) if c != spec["x"]][:6]
    elif kind == "scatter":
        pool = m_num if len(m_num) >= 2 else (varying if len(varying) > 1 else measured)
        spec["x"] = pool[0] if pool else None
        spec["y"] = pool[1:2]
        if categorical:
            spec["group"] = (m_cat or categorical)[0]
        if re.search(r"regress|回归|拟合|fit|trend ?line|趋势线", low):
            spec["fit"] = True
    elif kind == "hist":
        spec["x"] = (m_num or varying or [None])[0]
        spec["y"] = []
    elif kind == "heatmap":
        spec["x"] = categorical[0] if categorical else None
        spec["y"] = m_num or numeric
    if re.search(r"t[- ]?test|t检验|anova|方差分析|significan|显著|p ?值|p-?value|mann|wilcoxon|kruskal"
                 r"|检验|组间比较|两两比较|post[- ]?hoc|星号|星标|compare (?:the )?groups?|group comparison", low):
        spec["stats"] = True
    if re.search(r"error ?bar|误差|sem\b|标准误|sd\b|标准差", low):
        spec["error"] = "sd" if re.search(r"\bsd\b|标准差", low) else "sem"
    if re.search(r"(?:x|横)\s*轴?.{0,4}(?:取)?(?:log|对数)|log.{0,8}x[- ]?axis", low):
        spec["logx"] = True
    elif re.search(r"log.{0,6}(scale|y)|对数", low):
        spec["logy"] = True
    return spec


_PLOT_EDIT_KEYS = ("stats", "error", "logy", "logx", "fit")


def plot_edit(prompt: str, columns: list[dict], current: dict | None = None) -> dict:
    """Change an existing chart from a sentence ("改成箱线图，加显著性", "no error bars, log scale").

    Without a current chart this is :func:`plot_spec`. With one, only what the
    sentence mentions changes; everything else is kept.
    """
    if not current:
        return plot_spec(prompt, columns)
    low = (prompt or "").lower()
    out = dict(current)
    names = {c["name"] for c in columns}
    kind = next((k for k, words in _PLOT_WORDS if any(w in low for w in words)), None)
    fresh = plot_spec(prompt, columns)
    mentioned = [c["name"] for c in columns if c["name"] and c["name"].lower() in low]
    if kind and kind != current.get("kind"):
        out["kind"] = kind
        # Keep the columns when they still make sense for the new kind, else take the fresh guess.
        if kind in ("hist", "heatmap", "volcano", "scatter", "line") or mentioned:
            for key in ("x", "y", "group", "label"):
                if fresh.get(key) not in (None, "", []):
                    out[key] = fresh[key]
    elif mentioned:
        for key in ("x", "y", "group"):
            if fresh.get(key) not in (None, "", []):
                out[key] = fresh[key]
    for key in _PLOT_EDIT_KEYS:
        if fresh.get(key):
            out[key] = fresh[key]
    if re.search(r"(?:no|without|remove|去掉|不要|取消|删除).{0,8}(?:error ?bars?|误差)", low):
        out["error"] = None
    if re.search(r"(?:no|without|remove|去掉|不要|取消|删除).{0,8}(?:stat|significan|bracket|显著|星号|统计)", low):
        out["stats"] = False
    if re.search(r"(?:no|without|remove|hide|去掉|不要|取消|隐藏).{0,8}(?:points?|dots?|散点|数据点)", low):
        out["points"] = False
    elif re.search(r"(?:show|add|with|显示|加上?|添加).{0,8}(?:data ?points?|dots?|数据点|散点)", low):
        out["points"] = True
    if re.search(r"non-?param|mann|wilcoxon|kruskal|非参数|秩和", low):
        out["test"], out["stats"] = "nonparametric", True
    elif re.search(r"t[- ]?test|t检验|anova|方差分析|tukey", low):
        out["test"], out["stats"] = "parametric", True
    if re.search(r"ci ?95|95 ?% ?ci|置信区间", low):
        out["error"] = "ci95"
    if re.search(r"linear scale|线性(?:坐标|刻度)|(?:no|取消|去掉).{0,6}(?:log|对数)", low):
        out["logy"] = out["logx"] = False
    if re.search(r"色盲|colou?r-?blind|okabe", low):
        out["palette"] = "okabe"
    elif re.search(r"viridis", low):
        out["palette"] = "viridis"
    elif re.search(r"灰度|黑白|gr[ae]yscale|mono", low):
        out["palette"] = "mono"
    for key, pat in (
        ("title", r"(?:标题|title)\s*(?:改成|改为|设为|换成|为|是|to|:|：|=)\s*[\"“「']?([^\"”」'，,。;；\n]{1,80})"),
        ("xlabel", r"(?:x\s*轴(?:标签|名称|标题)?|横轴(?:标签|名称|标题)?|x[- ]?(?:axis )?label)\s*(?:改成|改为|设为|换成|为|是|to|:|：|=)\s*[\"“「']?([^\"”」'，,。;；\n]{1,60})"),
        ("ylabel", r"(?:y\s*轴(?:标签|名称|标题)?|纵轴(?:标签|名称|标题)?|y[- ]?(?:axis )?label)\s*(?:改成|改为|设为|换成|为|是|to|:|：|=)\s*[\"“「']?([^\"”」'，,。;；\n]{1,60})"),
    ):
        m = re.search(pat, prompt or "", re.I)
        if m:
            out[key] = m.group(1).strip()
    for key in ("x", "group", "label"):
        if out.get(key) and out[key] not in names:
            out[key] = None
    if isinstance(out.get("y"), list):
        out["y"] = [c for c in out["y"] if c in names]
    return out
