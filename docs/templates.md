# Templates: the content each builder expects

A template takes content you already have, as JSON, and lays it out. No model is
involved, nothing is sent anywhere, and the same content always gives the same
figure. This is the path to use when you know what the figure must say.

```bash
figwright template flowchart my-content.json -o figure.pptx
```

In the app the same builders sit behind **New figure → Templates**, and the MCP
tool is `build_template` (ask for a shape with `describe_template`).

Rules that hold for every kind:

- Unknown keys are ignored, so you can keep your own fields alongside.
- Text is wrapped and the boxes are sized to fit; you do not set coordinates.
- `title` is optional everywhere; leave it out and no title band is drawn.
- Anything the builder cannot place is reported rather than dropped silently:
  the CLI prints `check: …`, the app shows it in the issues panel.

---

## flowchart

```json
{
  "title": "",
  "direction": "TB",
  "nodes": [
    { "id": "n1", "text": "Start", "kind": "start" },
    { "id": "n2", "text": "Collect samples", "kind": "process" },
    { "id": "n3", "text": "Extract RNA", "kind": "process" },
    { "id": "n4", "text": "QC passed?", "kind": "decision" },
    { "id": "n5", "text": "Library prep and sequencing", "kind": "process" },
    { "id": "n6", "text": "End", "kind": "end" }
  ],
  "edges": [
    { "from": "n1", "to": "n2" },
    { "from": "n2", "to": "n3" },
    { "from": "n3", "to": "n4" },
    { "from": "n4", "to": "n5", "label": "Yes" },
    { "from": "n4", "to": "n3", "label": "No" },
    { "from": "n5", "to": "n6" }
  ]
}
```

- `direction`: `TB` (top to bottom, the default) or `LR` (left to right).
- `kind`: `start`, `end`, `process`, `subprocess`, `decision`, `io`, `data`,
  `note`. Common words are accepted too (`step`, `action`, `task`, `condition`,
  `branch`, `input`, `output`, `database`, `begin`, `stop`, …). A `decision` is
  drawn as a diamond and should read as a question; its outgoing edges want
  labels. An unknown kind is reported, not guessed.
- An edge back to an earlier node is routed around the column, so loops
  ("no, do it again") are fine.

## workflow

An experimental procedure as a numbered band of steps.

```json
{
  "title": "",
  "steps": [
    { "title": "Mouse model", "detail": "High-fat diet, 12 weeks", "icon": "mouse" },
    { "title": "Treatment", "detail": "Daily gavage, 4 weeks", "icon": "syringe" },
    { "title": "Tissue collection", "detail": "Liver and serum", "icon": "scissors" },
    { "title": "scRNA-seq", "detail": "10x Genomics", "icon": "dna" },
    { "title": "Analysis", "detail": "Clustering, DE genes", "icon": "chart" }
  ]
}
```

- `detail` is optional and set in a smaller size under the title.
- `icon` is optional; the name comes from `GET /api/icons` (or
  `figwright.icons.icon_catalog()`). An unknown name draws no icon rather than
  a broken one. Leave it out and Figwright picks one from the words.

## pathway

A signalling pathway: who acts on whom, and how.

```json
{
  "title": "MAPK signalling",
  "entities": [
    { "id": "egf",  "name": "EGF",  "type": "ligand" },
    { "id": "egfr", "name": "EGFR", "type": "receptor" },
    { "id": "ras",  "name": "RAS",  "type": "kinase" },
    { "id": "erk",  "name": "ERK",  "type": "kinase" },
    { "id": "myc",  "name": "MYC",  "type": "tf" },
    { "id": "prolif", "name": "Proliferation", "type": "process" },
    { "id": "drug", "name": "MEK inhibitor", "type": "drug" }
  ],
  "relations": [
    { "from": "egf", "to": "egfr", "type": "bind" },
    { "from": "egfr", "to": "ras", "type": "activate" },
    { "from": "ras", "to": "erk", "type": "activate" },
    { "from": "erk", "to": "myc", "type": "phosphorylate" },
    { "from": "myc", "to": "prolif", "type": "activate" },
    { "from": "drug", "to": "erk", "type": "inhibit" }
  ]
}
```

- `type` on an entity decides the shape and the band it sits in: `ligand`,
  `receptor`, `protein`, `kinase`, `tf` (transcription factor), `gene`, `rna`,
  `complex`, `molecule`, `drug`, `process`. Many synonyms are accepted
  (`cytokine`, `growth factor`, `gpcr`, `transporter`, `enzyme`, `phosphatase`,
  `metabolite`, `lipid`, `ion`, `mrna`, `mirna`, `antibody`, `inhibitor`,
  `phenotype`, `outcome`, …). Ligands sit on top, receptors in the membrane,
  genes and transcription factors in the nucleus band, processes at the bottom.
  Leave the type out and Figwright guesses it from the name (anything ending in
  `R` or `-receptor` is a receptor, `…mRNA` is RNA, and so on).
- `location` (or `compartment`) on an entity overrides that: `extracellular`,
  `membrane`, `cytoplasm`, `nucleus`.
- `type` on a relation decides the arrow head: `activate` (arrow), `inhibit`
  (bar), `bind` (plain line), `translocate` (dashed arrow), `indirect` (dashed),
  `indirect_inhibit` (dashed bar). Synonyms again work: `phosphorylate`,
  `transcribe`, `translate`, `secrete`, `recruit`, `degrade`, `upregulate`,
  `downregulate`, `->`, `-|`, `+`, `-`.

## abstract

A graphical abstract: problem, approach, finding, takeaway.

```json
{
  "title": "A 30-minute paper strip detects resistant bacteria",
  "panels": [
    { "heading": "Problem",  "icon": "bacterium", "bullets": ["Resistant infections are rising", "Culture takes 2 to 3 days"] },
    { "heading": "Approach", "icon": "scissors",  "bullets": ["CRISPR-based paper strip", "No instrument, 30-minute readout"] },
    { "heading": "Finding",  "icon": "chart",     "bullets": ["120 clinical samples", "Close agreement with culture"] }
  ],
  "takeaway": "Strip testing is suitable for point-of-care screening."
}
```

- Two to four panels read best; more are laid out but get narrow.
- `takeaway` is the sentence across the bottom. Optional.

## poster

A conference poster, laid out in A-series portrait proportions (print it at any
A size; A0 is 841 mm wide).

```json
{
  "title": "Gut microbiome diversity and sleep quality",
  "authors": "First Author, Second Author",
  "affiliations": "Department, University",
  "columns": 3,
  "sections": [
    { "heading": "Background", "body": "• Sleep disorders are increasingly common\n• The gut-brain axis may regulate sleep" },
    { "heading": "Methods", "body": "• 200 adult volunteers\n• Stool 16S rRNA sequencing", "figure": "Study design" },
    { "heading": "Results", "body": "• Lower diversity in the poor-sleep group", "figure": "Diversity comparison" },
    { "heading": "Conclusions", "body": "• Diversity may be a marker of sleep quality" }
  ]
}
```

- `columns`: 2, 3 or 4. Left out, Figwright picks from how much text there is.
- `figure` reserves a placeholder box with that caption, for you to drop a real
  figure into afterwards in the editor.
- `contact` adds a line along the bottom; `authors` and `affiliations` go under
  the title. All three are optional.
- Sections are poured into the columns in order, and the body font size is
  chosen (down to a floor) so that everything fits on one sheet. If it still
  does not fit, that is reported rather than clipped.

## prisma

A PRISMA 2020 flow diagram. Give the numbers you have; the derived ones are
computed and the boxes you leave out are not drawn.

```json
{
  "identified": [
    { "name": "PubMed", "n": 820 },
    { "name": "Embase", "n": 640 },
    { "name": "Cochrane", "n": 95 }
  ],
  "duplicates": 410,
  "automation": 0,
  "other_removed": 0,
  "screened": 1145,
  "excluded": 980,
  "sought": 165,
  "not_retrieved": 5,
  "assessed": 160,
  "excluded_reports": [
    { "reason": "Wrong study design", "n": 70 },
    { "reason": "Wrong outcome", "n": 48 },
    { "reason": "Incomplete data", "n": 12 }
  ],
  "included_studies": 30,
  "included_reports": 30
}
```

- `identified` may also be a single number when you do not want it split by
  database (`"identified": 1555`).
- The numbers are checked against each other: a column that does not add up is
  reported as `check: …` and the figure is still drawn, because your numbers are
  not Figwright's to change.
- `registers` works like `identified` for trial registers and draws the second
  identification box.

---

## Offline parsing instead of JSON

If you would rather write a sentence than JSON, `figwright generate` will parse
one into the same content shape without a model:

```bash
figwright generate "采样、提取、质检，如果合格则测序，否则重新提取" --kind flowchart -o fig.svg
figwright generate "identified 1555, 410 duplicates, 1145 screened, 980 excluded, 160 assessed, 30 included" --kind prisma -o prisma.svg
```

This is what "offline demo" means in the app: arrows (`A -> B`), numbered or
bulleted steps, `if … then …` / `如果……则……`, and `n = …` counts are understood.
It is a convenience, not a language model, and it says so on the figure's
record.
