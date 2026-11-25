# Examples

Content files you can run straight away, in English and Chinese
(`*.zh.json`). Nothing here needs a model.

## Templates

```bash
figwright template flowchart examples/flowchart.json -o flowchart.svg
figwright template workflow  examples/workflow.zh.json -o 实验流程.pptx
figwright template pathway   examples/pathway.json  -o pathway.pptx --theme okabe
figwright template abstract  examples/abstract.json -o abstract.png --width-mm 183 --dpi 600
figwright template poster    examples/poster.json   -o poster.pdf
figwright template prisma    examples/prisma.json   -o prisma.svg
```

The shape each file follows is documented in [../docs/templates.md](../docs/templates.md).

## Charts

`tumour-volume.csv` is three groups of eight animals: a comparison with a real
difference in it.

```bash
# box plot, group comparison, significance brackets, and a methods sentence
figwright plot examples/tumour-volume.csv -o tumour.png --kind box --stats --dpi 600

# the same data as a native, editable PowerPoint chart
# (name the column, or it charts every numeric one it finds, body weight included)
figwright plot examples/tumour-volume.csv -o tumour.pptx --kind bar --y tumour_volume_mm3 --error sem

# non-parametric instead, when the data do not look normal
figwright plot examples/tumour-volume.csv -o tumour.svg --kind violin --stats --test nonparametric
```

`dose-response.csv` is a six-point dose series in triplicate, for a log x axis
and a fit.

```bash
figwright plot examples/dose-response.csv -o dose.svg \
  --kind scatter --x concentration_uM --y response_percent --logx --fit
```

## Describing a figure in words, with no model connected

```bash
figwright generate "采样、提取 RNA、质检，如果合格则建库测序，否则重新提取" --kind flowchart -o qc.svg
figwright generate "EGF -> EGFR -> RAS -> RAF -> MEK -> ERK -> proliferation; MEK inhibitor -| MEK" --kind pathway -o mapk.svg
figwright generate "identified 1555, 410 duplicates removed, 1145 screened, 980 excluded, 165 sought, 160 assessed, 30 included" --kind prisma -o prisma.svg
```

Each of those says `offline demo: built with text rules, no AI model was used`
and records it on the figure, so the provenance stays honest.
