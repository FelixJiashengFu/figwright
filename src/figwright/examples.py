"""Example prompts and ready-made templates shown in the app.

All wording and data here were written for Figwright. The numbers in the
sample tables are made up for demonstration and say so in the app.
"""

from __future__ import annotations

# One example request per figure kind, in both interface languages.
EXAMPLES: dict[str, dict[str, str]] = {
    "flowchart": {
        "zh": "流程图：收集样本，提取RNA，质检是否合格？如果合格则建库测序，否则重新提取，最后数据分析",
        "en": "Flowchart: collect samples. Extract RNA. Is QC OK? If yes, build the library; otherwise re-extract. Then sequence and analyse.",
    },
    "workflow": {
        "zh": "实验流程：小鼠造模（高脂饮食 12 周），给药处理（每日灌胃 4 周），取材（肝脏与血清），单细胞测序，生信分析，验证实验（qPCR 与免疫组化）",
        "en": "Workflow: induce the mouse model (high-fat diet, 12 weeks), treat (daily gavage, 4 weeks), collect tissue (liver and serum), single-cell sequencing, bioinformatic analysis, validation (qPCR and IHC)",
    },
    "pathway": {
        "zh": "信号通路：EGF 结合 EGFR，EGFR 激活 RAS，RAS 激活 RAF，RAF 激活 MEK，MEK 激活 ERK，ERK 进入细胞核激活 MYC，药物 抑制 MEK",
        "en": "Pathway: EGF binds EGFR. EGFR activates RAS, RAS activates RAF, RAF activates MEK, MEK activates ERK. ERK translocates to the nucleus and activates MYC. Trametinib inhibits MEK.",
    },
    "abstract": {
        "zh": "图文摘要。问题：抗生素耐药菌感染缺乏快速诊断手段。方法：我们开发了基于 CRISPR 的试纸条检测，30 分钟出结果。发现：在 120 份临床样本中与培养法结果高度一致。结论：该方法可用于基层快速筛查。",
        "en": "Graphical abstract. Problem: infections with resistant bacteria lack a rapid test. Approach: a CRISPR-based paper strip that reads out in 30 minutes. Finding: close agreement with culture in 120 clinical samples. Conclusion: suitable for point-of-care screening.",
    },
    "poster": {
        "zh": "学术海报。标题：肠道菌群与睡眠质量的关联研究。背景：睡眠障碍发病率逐年上升。方法：招募 200 名志愿者，采集粪便样本并做 16S 测序，同时记录睡眠日志。结果：睡眠质量较差组菌群多样性显著降低。结论：菌群多样性可能是睡眠质量的潜在指标。",
        "en": "Poster. Title: Gut microbiome diversity and sleep quality. Background: sleep disorders are increasingly common. Methods: 200 volunteers, stool 16S sequencing, sleep diaries. Results: lower diversity in the poor-sleep group. Conclusions: diversity may be a marker of sleep quality.",
    },
    "prisma": {
        "zh": "PRISMA 流程图：PubMed 检索到 820 篇，Embase 检索到 640 篇，Cochrane 检索到 95 篇；去除重复 410 篇；筛选 1145 篇，排除 980 篇；获取全文 165 篇，未获取 5 篇；评估 160 篇，排除：研究设计不符 70 篇，结局指标不符 48 篇，数据不全 12 篇；最终纳入 30 项研究",
        "en": "PRISMA: PubMed 820, Embase 640, Cochrane 95; duplicates removed 410; screened 1145, excluded 980; sought 165, not retrieved 5; assessed 160; excluded: wrong design 70, wrong outcome 48, incomplete data 12; included 30 studies",
    },
    "illustration": {
        "zh": "示意图：线粒体功能障碍如何导致神经元凋亡。包括活性氧升高、膜电位下降、细胞色素 c 释放、caspase 激活四个环节，并标出两个可能的药物干预点。",
        "en": "Schematic: how mitochondrial dysfunction leads to neuronal apoptosis. Show rising ROS, loss of membrane potential, cytochrome c release and caspase activation, and mark two possible drug intervention points.",
    },
}

IMAGE_EXAMPLES = {
    "zh": "人体肝脏的解剖示意图，显示左右叶、胆囊和主要血管",
    "en": "Anatomy of the human liver showing both lobes, the gallbladder and the main vessels",
}

_SAMPLE_BARS = """group,value
Control,9.8
Control,10.6
Control,8.9
Control,11.2
Control,10.1
Control,9.4
Drug A,12.9
Drug A,13.8
Drug A,12.1
Drug A,14.4
Drug A,13.0
Drug A,12.6
Drug B,16.2
Drug B,17.9
Drug B,15.8
Drug B,18.4
Drug B,16.9
Drug B,17.1
Drug A+B,21.0
Drug A+B,23.2
Drug A+B,20.4
Drug A+B,24.1
Drug A+B,22.3
Drug A+B,21.7
"""

_PRISMA = {
    "identified": [{"name": "PubMed", "n": 820}, {"name": "Embase", "n": 640}, {"name": "Cochrane", "n": 95}],
    "duplicates": 410,
    "automation": 0,
    "other_removed": 0,
    "screened": 1145,
    "excluded": 980,
    "sought": 165,
    "not_retrieved": 5,
    "assessed": 160,
    "included_studies": 30,
    "included_reports": 30,
}

# The template gallery. "builder" templates are laid out by a deterministic builder
# from the content below; "plot" opens the chart page with the sample table;
# "illustrate" opens the illustration page with a starting request.
TEMPLATE_FORMS: list[dict] = [
    {
        "id": "abstract",
        "type": "builder",
        "kind": "abstract",
        "icon": "lightbulb",
        "label": {"zh": "图文摘要", "en": "Graphical abstract"},
        "desc": {"zh": "两到四栏，从问题讲到结论", "en": "Two to four panels, from problem to takeaway"},
        "content": {
            "zh": {
                "title": "30 分钟试纸条快速检出耐药菌",
                "panels": [
                    {"heading": "问题", "icon": "bacterium", "bullets": ["耐药菌感染日益增多", "培养法需要 2 到 3 天"]},
                    {"heading": "方法", "icon": "scissors", "bullets": ["基于 CRISPR 的试纸条", "无需仪器，30 分钟读数"]},
                    {"heading": "发现", "icon": "chart", "bullets": ["120 份临床样本", "与培养法结果高度一致"]},
                ],
                "takeaway": "试纸条检测可用于基层的快速筛查。",
            },
            "en": {
                "title": "A 30-minute paper strip detects resistant bacteria",
                "panels": [
                    {"heading": "Problem", "icon": "bacterium", "bullets": ["Resistant infections are rising", "Culture takes 2 to 3 days"]},
                    {"heading": "Approach", "icon": "scissors", "bullets": ["CRISPR-based paper strip", "No instrument, 30-minute readout"]},
                    {"heading": "Finding", "icon": "chart", "bullets": ["120 clinical samples", "Close agreement with culture"]},
                ],
                "takeaway": "Strip testing is suitable for point-of-care screening.",
            },
        },
    },
    {
        "id": "pathway",
        "type": "builder",
        "kind": "pathway",
        "icon": "receptor",
        "label": {"zh": "信号通路", "en": "Signalling pathway"},
        "desc": {"zh": "按胞外、膜、胞质、细胞核自动分层", "en": "Sorted into extracellular, membrane, cytoplasm and nucleus"},
        "content": {
            "zh": {
                "title": "MAPK 信号通路",
                "entities": [
                    {"id": "egf", "name": "EGF", "type": "ligand"},
                    {"id": "egfr", "name": "EGFR", "type": "receptor"},
                    {"id": "ras", "name": "RAS", "type": "kinase"},
                    {"id": "raf", "name": "RAF", "type": "kinase"},
                    {"id": "mek", "name": "MEK", "type": "kinase"},
                    {"id": "erk", "name": "ERK", "type": "kinase"},
                    {"id": "myc", "name": "MYC", "type": "tf"},
                    {"id": "prolif", "name": "细胞增殖", "type": "process"},
                    {"id": "drug", "name": "MEK 抑制剂", "type": "drug"},
                ],
                "relations": [
                    {"from": "egf", "to": "egfr", "type": "bind"},
                    {"from": "egfr", "to": "ras", "type": "activate"},
                    {"from": "ras", "to": "raf", "type": "activate"},
                    {"from": "raf", "to": "mek", "type": "activate", "label": "P"},
                    {"from": "mek", "to": "erk", "type": "activate", "label": "P"},
                    {"from": "erk", "to": "myc", "type": "translocate"},
                    {"from": "myc", "to": "prolif", "type": "activate"},
                    {"from": "drug", "to": "mek", "type": "inhibit"},
                ],
            },
            "en": {
                "title": "MAPK signalling",
                "entities": [
                    {"id": "egf", "name": "EGF", "type": "ligand"},
                    {"id": "egfr", "name": "EGFR", "type": "receptor"},
                    {"id": "ras", "name": "RAS", "type": "kinase"},
                    {"id": "raf", "name": "RAF", "type": "kinase"},
                    {"id": "mek", "name": "MEK", "type": "kinase"},
                    {"id": "erk", "name": "ERK", "type": "kinase"},
                    {"id": "myc", "name": "MYC", "type": "tf"},
                    {"id": "prolif", "name": "Proliferation", "type": "process"},
                    {"id": "drug", "name": "MEK inhibitor", "type": "drug"},
                ],
                "relations": [
                    {"from": "egf", "to": "egfr", "type": "bind"},
                    {"from": "egfr", "to": "ras", "type": "activate"},
                    {"from": "ras", "to": "raf", "type": "activate"},
                    {"from": "raf", "to": "mek", "type": "activate", "label": "P"},
                    {"from": "mek", "to": "erk", "type": "activate", "label": "P"},
                    {"from": "erk", "to": "myc", "type": "translocate"},
                    {"from": "myc", "to": "prolif", "type": "activate"},
                    {"from": "drug", "to": "mek", "type": "inhibit"},
                ],
            },
        },
    },
    {
        "id": "prisma",
        "type": "builder",
        "kind": "prisma",
        "icon": "funnel",
        "form": "prisma",
        # The web client builds a small form from this instead of a canned example,
        # because a PRISMA diagram is only ever as good as the reviewer's own counts.
        "fields": [
            {"id": "identified", "kind": "sources", "label": {"zh": "各数据库检出记录", "en": "Records found in each database"}},
            {"id": "duplicates", "kind": "number", "label": {"zh": "去重后删除", "en": "Duplicates removed"}},
            {"id": "automation", "kind": "number", "label": {"zh": "自动工具标记删除", "en": "Removed by automation tools"}},
            {"id": "other_removed", "kind": "number", "label": {"zh": "其他原因删除", "en": "Removed for other reasons"}},
            {"id": "screened", "kind": "number", "label": {"zh": "筛选的记录", "en": "Records screened"}},
            {"id": "excluded", "kind": "number", "label": {"zh": "筛选阶段排除", "en": "Records excluded"}},
            {"id": "sought", "kind": "number", "label": {"zh": "寻找全文", "en": "Reports sought for retrieval"}},
            {"id": "not_retrieved", "kind": "number", "label": {"zh": "未获取全文", "en": "Reports not retrieved"}},
            {"id": "assessed", "kind": "number", "label": {"zh": "全文评估", "en": "Reports assessed for eligibility"}},
            {"id": "excluded_reports", "kind": "reasons", "label": {"zh": "全文排除及原因", "en": "Reports excluded, with reasons"}},
            {"id": "included_studies", "kind": "number", "label": {"zh": "纳入研究数", "en": "Studies included"}},
            {"id": "included_reports", "kind": "number", "label": {"zh": "纳入报告数", "en": "Reports of included studies"}},
        ],
        "label": {"zh": "PRISMA 2020 流程图", "en": "PRISMA 2020 flow diagram"},
        "desc": {"zh": "填数字即可，程序核对前后是否对得上", "en": "Fill in the counts; the arithmetic is checked for you"},
        "content": {
            "zh": {**_PRISMA, "title": "", "excluded_reports": [{"reason": "研究设计不符", "n": 70}, {"reason": "结局指标不符", "n": 48}, {"reason": "数据不全", "n": 12}]},
            "en": {**_PRISMA, "title": "", "excluded_reports": [{"reason": "Wrong study design", "n": 70}, {"reason": "Wrong outcome", "n": 48}, {"reason": "Incomplete data", "n": 12}]},
        },
    },
    {
        "id": "workflow",
        "type": "builder",
        "kind": "workflow",
        "icon": "flask",
        "label": {"zh": "实验流程", "en": "Experimental workflow"},
        "desc": {"zh": "带图标的步骤卡片，自动折行", "en": "Step cards with icons that wrap into rows"},
        "content": {
            "zh": {
                "title": "",
                "steps": [
                    {"title": "小鼠造模", "detail": "高脂饮食 12 周", "icon": "mouse"},
                    {"title": "给药处理", "detail": "每日灌胃 4 周", "icon": "syringe"},
                    {"title": "取材", "detail": "肝脏与血清", "icon": "scissors"},
                    {"title": "单细胞测序", "detail": "10x Genomics", "icon": "dna"},
                    {"title": "生信分析", "detail": "聚类与差异表达", "icon": "chart"},
                    {"title": "验证实验", "detail": "qPCR 与免疫组化", "icon": "check"},
                ],
            },
            "en": {
                "title": "",
                "steps": [
                    {"title": "Mouse model", "detail": "High-fat diet, 12 weeks", "icon": "mouse"},
                    {"title": "Treatment", "detail": "Daily gavage, 4 weeks", "icon": "syringe"},
                    {"title": "Tissue collection", "detail": "Liver and serum", "icon": "scissors"},
                    {"title": "scRNA-seq", "detail": "10x Genomics", "icon": "dna"},
                    {"title": "Analysis", "detail": "Clustering, DE genes", "icon": "chart"},
                    {"title": "Validation", "detail": "qPCR and IHC", "icon": "check"},
                ],
            },
        },
    },
    {
        "id": "flowchart",
        "type": "builder",
        "kind": "flowchart",
        "icon": "network",
        "label": {"zh": "流程图", "en": "Flowchart"},
        "desc": {"zh": "带判断分支和回环的标准流程图", "en": "Decisions, branches and loops"},
        "content": {
            "zh": {
                "title": "",
                "direction": "TB",
                "nodes": [
                    {"id": "n1", "text": "开始", "kind": "start"},
                    {"id": "n2", "text": "收集样本", "kind": "process"},
                    {"id": "n3", "text": "提取 RNA", "kind": "process"},
                    {"id": "n4", "text": "质检是否合格？", "kind": "decision"},
                    {"id": "n5", "text": "建库测序", "kind": "process"},
                    {"id": "n6", "text": "数据分析", "kind": "process"},
                    {"id": "n7", "text": "结束", "kind": "end"},
                ],
                "edges": [
                    {"from": "n1", "to": "n2"},
                    {"from": "n2", "to": "n3"},
                    {"from": "n3", "to": "n4"},
                    {"from": "n4", "to": "n5", "label": "是"},
                    {"from": "n4", "to": "n3", "label": "否"},
                    {"from": "n5", "to": "n6"},
                    {"from": "n6", "to": "n7"},
                ],
            },
            "en": {
                "title": "",
                "direction": "TB",
                "nodes": [
                    {"id": "n1", "text": "Start", "kind": "start"},
                    {"id": "n2", "text": "Collect samples", "kind": "process"},
                    {"id": "n3", "text": "Extract RNA", "kind": "process"},
                    {"id": "n4", "text": "QC passed?", "kind": "decision"},
                    {"id": "n5", "text": "Library prep and sequencing", "kind": "process"},
                    {"id": "n6", "text": "Data analysis", "kind": "process"},
                    {"id": "n7", "text": "End", "kind": "end"},
                ],
                "edges": [
                    {"from": "n1", "to": "n2"},
                    {"from": "n2", "to": "n3"},
                    {"from": "n3", "to": "n4"},
                    {"from": "n4", "to": "n5", "label": "Yes"},
                    {"from": "n4", "to": "n3", "label": "No"},
                    {"from": "n5", "to": "n6"},
                    {"from": "n6", "to": "n7"},
                ],
            },
        },
    },
    {
        "id": "poster",
        "type": "builder",
        "kind": "poster",
        "icon": "document",
        "label": {"zh": "学术海报", "en": "Conference poster"},
        "desc": {"zh": "标题栏加分栏正文，留好图位", "en": "Title band, columns and figure placeholders"},
        "content": {
            "zh": {
                "title": "肠道菌群多样性与睡眠质量的关联",
                "authors": "作者一，作者二，作者三",
                "affiliations": "某某大学 某某学院",
                "columns": 3,
                "sections": [
                    {"heading": "背景", "body": "• 睡眠障碍发病率逐年上升\n• 肠脑轴可能参与睡眠调节\n• 人群证据仍然有限", "figure": None},
                    {"heading": "方法", "body": "• 招募 200 名成年志愿者\n• 粪便 16S rRNA 测序\n• 连续两周睡眠日志", "figure": "研究流程图"},
                    {"heading": "结果", "body": "• 睡眠较差组菌群多样性显著降低\n• 若干菌属丰度与睡眠评分相关", "figure": "多样性比较图"},
                    {"heading": "结论", "body": "• 菌群多样性可能是睡眠质量的潜在指标\n• 因果关系仍需干预研究验证", "figure": None},
                    {"heading": "参考文献", "body": "在这里填写参考文献。", "figure": None},
                ],
                "contact": "联系邮箱：name@example.org",
            },
            "en": {
                "title": "Gut microbiome diversity and sleep quality",
                "authors": "First Author, Second Author, Third Author",
                "affiliations": "Department, University",
                "columns": 3,
                "sections": [
                    {"heading": "Background", "body": "• Sleep disorders are increasingly common\n• The gut-brain axis may regulate sleep\n• Evidence in humans is limited", "figure": None},
                    {"heading": "Methods", "body": "• 200 adult volunteers\n• Stool 16S rRNA sequencing\n• Two-week sleep diaries", "figure": "Study design"},
                    {"heading": "Results", "body": "• Lower diversity in the poor-sleep group\n• Several genera correlate with sleep scores", "figure": "Diversity comparison"},
                    {"heading": "Conclusions", "body": "• Diversity may be a marker of sleep quality\n• Causality needs intervention studies", "figure": None},
                    {"heading": "References", "body": "List your references here.", "figure": None},
                ],
                "contact": "Contact: name@example.org",
            },
        },
    },
    {
        "id": "medical",
        "type": "illustrate",
        "style": "medical",
        "icon": "heart",
        "label": {"zh": "医学插画", "en": "Medical illustration"},
        "desc": {"zh": "由图像模型作画，文字标注之后手动加", "en": "Painted by an image model; labels are added as real text"},
        "content": {"zh": IMAGE_EXAMPLES["zh"], "en": IMAGE_EXAMPLES["en"]},
    },
    {
        "id": "bar",
        "type": "plot",
        "icon": "chart",
        "label": {"zh": "柱状图加显著性", "en": "Bar chart with statistics"},
        "desc": {"zh": "示例数据是编的，换成你自己的表", "en": "The sample numbers are made up: replace them with your table"},
        "csv": _SAMPLE_BARS,
        "spec": {"kind": "bar", "x": "group", "y": ["value"], "error": "sem", "stats": True, "points": True},
    },
]
