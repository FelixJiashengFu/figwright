/* Chinese and English wording for the interface. Keys match data-i / data-i-ph in index.html. */

export const STRINGS = {
  zh: {
    'tab.draw': '画图', 'tab.plot': '数据图', 'tab.image': '图片工坊', 'tab.projects': '项目', 'tab.settings': '设置',
    'flag.offline': '离线演示',
    'flag.offline.title': '还没有接模型，现在用内置规则排版。到“设置”里填一个密钥就能用上 AI。',
    'draw.make': '生成', 'draw.go': '生成', 'draw.example': '来个例子',
    'draw.prompt.ph': '描述你要的图，例如：样本采集 → DNA 提取 → 质检，如果合格则建库测序，否则重新提取 → 数据分析',
    'draw.source': '读入资料', 'draw.sketch': '草图转图', 'draw.import': '打开文件',
    'draw.templates': '模板', 'draw.illustrate': 'AI 插画', 'draw.ill.go': '画',
    'draw.ill.ph': '一个线粒体的示意图，扁平风格',
    'draw.chat': '对话修改', 'draw.refine': '修改',
    'draw.chat.ph': '例如：把质检那个框改成橙色；在测序后面加一步 比对',
    'draw.props': '属性', 'draw.layers': '图层', 'draw.tidy': '整理版面', 'draw.polish': 'AI 润色',
    'draw.save': '存档', 'draw.export': '导出', 'draw.lock': '锁定样式', 'draw.notes': '显示批注',
    'plot.data': '数据', 'plot.open': '打开表格', 'plot.paste': '粘贴', 'plot.ask': '一句话改图', 'plot.ask.go': '改',
    'plot.paste.ph': '直接粘贴几列数据，用逗号或制表符分隔',
    'plot.ask.ph': '例如：改成箱线图，加显著性标记，纵轴改成对数',
    'plot.spec': '图形设置', 'plot.stats': '统计',
    'image.open': '打开图片', 'image.choose': '选择照片、扫描件或截图', 'image.clean': '清理',
    'image.hint': '胶图、显微照片、手绘草图都行。处理都在你自己的电脑上完成。',
    'image.apply': '处理', 'image.reset': '还原', 'image.vector': '转矢量', 'image.colors': '颜色数',
    'image.detail': '细节', 'image.split': '每块一个形状', 'image.vgo': '描成矢量',
    'image.redraw': '局部重绘', 'image.redraw.hint': '在图上拖一个框，写一句要改成什么。',
    'image.redraw.ph': '例如：把这块背景换成浅灰', 'image.redraw.go': '重绘选中区域',
    'image.tocanvas': '放到画布', 'image.download': '下载',
    'proj.title': '项目', 'proj.refresh': '刷新', 'proj.versions': '历史版本',
    'set.roles': '模型分工', 'set.providers': '接口与密钥', 'set.house': '统一样式',
    'set.roles.hint': '不填也能用：离线模式用内置规则排版，只是不会动脑子。',
    'set.keys.hint': '密钥只存在这台电脑的 ~/.figwright/config.json 里，界面上永远只回显遮挡后的片段。',
    'set.house.hint': '锁定后，新生成的图都沿用同一套字体、线宽和圆角，一篇论文里的图就不会各长各的。',
    'busy.cancel': '取消',
    'role.text': '文字模型', 'role.vision': '看图模型', 'role.image': '出图模型',
    'role.text.hint': '负责把你的描述变成图的结构，也负责对话修改。',
    'role.vision.hint': '负责看草图、看渲染结果挑毛病。留空就用文字模型。',
    'role.image.hint': '负责 AI 插画和局部重绘。',
    'provider.none': '不使用', 'provider.model': '模型', 'provider.list': '列出模型', 'provider.test': '测试',
    'provider.key': '密钥', 'provider.key.set': '已保存', 'provider.key.env': '来自环境变量',
    'provider.save': '保存', 'provider.clear': '清除', 'provider.url': '接口地址',
    'export.title': '导出', 'export.format': '格式', 'export.size': '尺寸', 'export.dpi': '分辨率',
    'export.transparent': '透明背景', 'export.notes': '包含批注', 'export.go': '导出', 'export.print': '打印成矢量 PDF',
    'export.disclosure': '附上 AI 使用声明', 'export.record': '同时生成制作记录',
    'cancel': '取消', 'close': '关闭', 'ok': '好',
    'delete': '删除', 'open': '打开', 'rename': '重命名', 'duplicate': '复制', 'restore': '恢复',
    'untitled': '未命名',
    'err.network': '连不上本机服务，可能已经关掉了。',
    'saved': '已保存', 'copied': '已复制',
    'conflict': '这个项目在别处被改过了。要覆盖，还是先看看那一版？',
    'conflict.overwrite': '用我这版覆盖', 'conflict.reload': '读取那一版',
    'nothing.selected': '先选中一个对象',
    'confirm.delete': '删掉「{name}」？删了就找不回来了。',
  },
  en: {
    'tab.draw': 'Draw', 'tab.plot': 'Charts', 'tab.image': 'Image lab', 'tab.projects': 'Projects', 'tab.settings': 'Settings',
    'flag.offline': 'offline demo',
    'flag.offline.title': 'No model is connected, so figures are laid out by built-in rules. Add a key in Settings to use AI.',
    'draw.make': 'Generate', 'draw.go': 'Generate', 'draw.example': 'Try an example',
    'draw.prompt.ph': 'Describe the figure, e.g. collect samples -> extract DNA -> run QC, if it passes build the library, otherwise re-extract -> analyse',
    'draw.source': 'Read a file', 'draw.sketch': 'Sketch to figure', 'draw.import': 'Open a figure',
    'draw.templates': 'Templates', 'draw.illustrate': 'AI illustration', 'draw.ill.go': 'Draw',
    'draw.ill.ph': 'A mitochondrion, flat style',
    'draw.chat': 'Edit by chat', 'draw.refine': 'Apply',
    'draw.chat.ph': 'e.g. make the QC box orange; add a step called Alignment after sequencing',
    'draw.props': 'Properties', 'draw.layers': 'Layers', 'draw.tidy': 'Tidy layout', 'draw.polish': 'AI polish',
    'draw.save': 'Save', 'draw.export': 'Export', 'draw.lock': 'Lock house style', 'draw.notes': 'Show comments',
    'plot.data': 'Data', 'plot.open': 'Open a table', 'plot.paste': 'Paste', 'plot.ask': 'Change it in words', 'plot.ask.go': 'Apply',
    'plot.paste.ph': 'Paste a few columns, separated by commas or tabs',
    'plot.ask.ph': 'e.g. make it a box plot with significance marks and a log y axis',
    'plot.spec': 'Chart settings', 'plot.stats': 'Statistics',
    'image.open': 'Open a picture', 'image.choose': 'Choose a photo, scan or screenshot', 'image.clean': 'Clean up',
    'image.hint': 'Gels, micrographs and hand drawings all work. Everything runs on your own computer.',
    'image.apply': 'Apply', 'image.reset': 'Reset', 'image.vector': 'Trace to vector', 'image.colors': 'Colours',
    'image.detail': 'Detail', 'image.split': 'One shape per patch', 'image.vgo': 'Trace',
    'image.redraw': 'Redraw a region', 'image.redraw.hint': 'Drag a box on the picture, then say what it should become.',
    'image.redraw.ph': 'e.g. make this background light grey', 'image.redraw.go': 'Redraw the selected region',
    'image.tocanvas': 'Put on canvas', 'image.download': 'Download',
    'proj.title': 'Projects', 'proj.refresh': 'Refresh', 'proj.versions': 'Versions',
    'set.roles': 'Which model does what', 'set.providers': 'Providers and keys', 'set.house': 'House style',
    'set.roles.hint': 'Optional: with nothing set, Figwright lays figures out by rule. It just will not think.',
    'set.keys.hint': 'Keys live only in ~/.figwright/config.json on this computer, and the interface only ever shows a masked hint.',
    'set.house.hint': 'Lock it and every new figure keeps the same font, line width and corner radius, so one paper looks like one paper.',
    'busy.cancel': 'Cancel',
    'role.text': 'Text model', 'role.vision': 'Vision model', 'role.image': 'Image model',
    'role.text.hint': 'Turns your description into the structure of a figure, and handles edits by chat.',
    'role.vision.hint': 'Looks at sketches and at the drawn figure to catch mistakes. Falls back to the text model.',
    'role.image.hint': 'Draws AI illustrations and redraws regions.',
    'provider.none': 'Not used', 'provider.model': 'Model', 'provider.list': 'List models', 'provider.test': 'Test',
    'provider.key': 'API key', 'provider.key.set': 'saved', 'provider.key.env': 'from the environment',
    'provider.save': 'Save', 'provider.clear': 'Clear', 'provider.url': 'API address',
    'export.title': 'Export', 'export.format': 'Format', 'export.size': 'Size', 'export.dpi': 'Resolution',
    'export.transparent': 'Transparent background', 'export.notes': 'Include comments', 'export.go': 'Export',
    'export.print': 'Print a vector PDF', 'export.disclosure': 'Add the AI disclosure', 'export.record': 'Also make a provenance record',
    'cancel': 'Cancel', 'close': 'Close', 'ok': 'OK',
    'delete': 'Delete', 'open': 'Open', 'rename': 'Rename', 'duplicate': 'Duplicate', 'restore': 'Restore',
    'untitled': 'Untitled',
    'err.network': 'Cannot reach the local server; it may have been closed.',
    'saved': 'Saved', 'copied': 'Copied',
    'conflict': 'Someone else changed this project. Overwrite it, or look at their version first?',
    'conflict.overwrite': 'Overwrite with mine', 'conflict.reload': 'Load their version',
    'nothing.selected': 'Select something first',
    'confirm.delete': 'Delete "{name}"? This cannot be undone.',
  },
};

export const NAMES = {
  kind: {
    zh: { auto: '自动判断', illustration: '示意图', flowchart: '流程图', workflow: '实验流程', pathway: '信号通路', abstract: '图文摘要', poster: '海报', prisma: 'PRISMA' },
    en: { auto: 'Choose for me', illustration: 'Illustration', flowchart: 'Flowchart', workflow: 'Experimental workflow', pathway: 'Signalling pathway', abstract: 'Graphical abstract', poster: 'Poster', prisma: 'PRISMA' },
  },
  quality: {
    zh: { fast: '快', balanced: '标准', best: '最好（慢）' },
    en: { fast: 'Fast', balanced: 'Balanced', best: 'Best (slower)' },
  },
  node: {
    zh: { rect: '方框', ellipse: '椭圆', diamond: '菱形', hexagon: '六边形', parallelogram: '平行四边形', cylinder: '圆柱', pill: '圆角条', triangle: '三角形', text: '文字', frame: '分区框', note: '批注', icon: '图标', image: '图片', bilayer: '细胞膜', path: '路径' },
    en: { rect: 'Box', ellipse: 'Ellipse', diamond: 'Diamond', hexagon: 'Hexagon', parallelogram: 'Parallelogram', cylinder: 'Cylinder', pill: 'Pill', triangle: 'Triangle', text: 'Text', frame: 'Frame', note: 'Comment', icon: 'Icon', image: 'Picture', bilayer: 'Membrane', path: 'Path' },
  },
  head: {
    zh: { arrow: '箭头', inhibit: '抑制 ⊣', none: '无', both: '双向', circle: '圆点' },
    en: { arrow: 'Arrow', inhibit: 'Inhibit', none: 'None', both: 'Both ends', circle: 'Dot' },
  },
  routing: {
    zh: { straight: '直线', elbow: '折线', curve: '曲线' },
    en: { straight: 'Straight', elbow: 'Elbow', curve: 'Curve' },
  },
  plotKind: {
    zh: { bar: '柱状图', line: '折线图', scatter: '散点图', box: '箱线图', violin: '小提琴图', hist: '直方图', heatmap: '热图', pie: '饼图', volcano: '火山图' },
    en: { bar: 'Bar', line: 'Line', scatter: 'Scatter', box: 'Box', violin: 'Violin', hist: 'Histogram', heatmap: 'Heatmap', pie: 'Pie', volcano: 'Volcano' },
  },
  plotError: {
    zh: { sd: '标准差 SD', sem: '标准误 SEM', ci95: '95% 置信区间', none: '不画' },
    en: { sd: 'SD', sem: 'SEM', ci95: '95% CI', none: 'None' },
  },
  palette: {
    zh: { theme: '跟随主题', okabe: '色盲友好', viridis: 'Viridis', mono: '灰度' },
    en: { theme: 'Theme', okabe: 'Colour-blind safe', viridis: 'Viridis', mono: 'Greyscale' },
  },
  detail: { zh: { low: '粗', medium: '中', high: '细' }, en: { low: 'Low', medium: 'Medium', high: 'High' } },
  cvd: {
    zh: { '': '正常视觉', deuteranopia: '绿色盲预览', protanopia: '红色盲预览', tritanopia: '蓝色盲预览' },
    en: { '': 'Normal vision', deuteranopia: 'Deuteranopia', protanopia: 'Protanopia', tritanopia: 'Tritanopia' },
  },
  style: {
    zh: { flat: '扁平矢量', realistic: '写实', watercolor: '水彩', line: '线稿', '3d': '三维渲染', isometric: '等轴测' },
    en: { flat: 'Flat vector', realistic: 'Realistic', watercolor: 'Watercolour', line: 'Line art', '3d': '3D render', isometric: 'Isometric' },
  },
};

let lang = 'zh';

export function setLang(value) {
  lang = value === 'en' ? 'en' : 'zh';
  document.documentElement.lang = lang;
  for (const el of document.querySelectorAll('[data-i]')) {
    const s = STRINGS[lang][el.dataset.i];
    if (s !== undefined) el.textContent = s;
  }
  for (const el of document.querySelectorAll('[data-i-ph]')) {
    const s = STRINGS[lang][el.dataset.iPh];
    if (s !== undefined) el.placeholder = s;
  }
  const flag = document.getElementById('offline-flag');
  if (flag) flag.title = STRINGS[lang]['flag.offline.title'];
  const btn = document.getElementById('lang-btn');
  if (btn) btn.textContent = lang === 'zh' ? 'EN' : '中文';
  return lang;
}

export function getLang() { return lang; }

export function t(key, vars) {
  let s = STRINGS[lang][key] ?? STRINGS.zh[key] ?? key;
  if (vars) for (const [k, v] of Object.entries(vars)) s = s.replace(`{${k}}`, v);
  return s;
}

/** A readable name for a value of an enumerated setting. */
export function name(group, value) {
  const g = NAMES[group];
  if (!g) return value;
  return (g[lang] && g[lang][value]) || (g.zh && g.zh[value]) || value;
}
