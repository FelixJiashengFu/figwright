/* The engine speaks English. When the interface is in Chinese, these rules
 * translate the messages a user actually meets: layout checks, offline-demo
 * notes, and what an export did. Anything not listed is shown as it came,
 * which is better than a half-translated sentence.
 */

import { getLang } from './i18n.js';

const RULES = [
  [/^offline demo: built with text rules, no AI model was used$/, () => '离线演示：这张图是用内置规则排的，没有用到 AI'],
  [/^the model's answer was cut off at its output limit; the figure may be incomplete$/, () => '模型的回答在长度上限处被截断了，这张图可能不完整'],
  [/^updated (.+)$/, (m) => `改了 ${m[1]}`],
  [/^resized (\d+) /, (m) => `调整了 ${m[1]} 处大小，让文字放得下`],
  [/^aligned (\d+) /, (m) => `对齐了 ${m[1]} 处`],
  [/^extended the canvas/, () => '画布已经放大，免得内容被切掉'],
  [/^The figure has no elements\.$/, () => '这张图是空的。'],
  [/^The text of '(.+?)' does not fit its ([\d.]+)x([\d.]+) box\.$/, (m) => `「${m[1]}」的文字放不进 ${m[2]}×${m[3]} 的框。`],
  [/^The text of '(.+?)' is smaller than 9 px and will be unreadable in print\.$/, (m) => `「${m[1]}」的字小于 9 px，印出来看不清。`],
  [/^'(.+?)' and '(.+?)' overlap/, (m) => `「${m[1]}」和「${m[2]}」叠在一起了`],
  [/^Connector '(.+?)' runs across '(.+?)'\.$/, (m) => `连线 ${m[1]} 压过了「${m[2]}」。`],
  [/^This PDF holds a bitmap\./, () => '这个 PDF 里是位图。要矢量 PDF，用导出框里的「打印成矢量 PDF」，或者直接导出 SVG。'],
  [/^a connector with an unusual route was drawn as a free line/, () => '有一条走法特别的连线被画成了自由线条：形状保留，但挪动方框时它不会跟着走'],
  [/^traced at (\d+) x (\d+) px \(the original is (\d+) x (\d+)\)/, (m) => `按 ${m[1]}×${m[2]} 描的（原图 ${m[3]}×${m[4]}），要更细可以调高上限`],
  [/^text in the image becomes outlines, not editable text/, () => '图里的文字会变成轮廓，不再是可编辑文字；要保留文字请重新打一遍'],
  [/^this image has gradients or photographic detail/, () => '这张图有渐变或照片细节，描出来会有色块感；描图更适合线稿、图标和纯色示意图'],
  [/^transparent areas were kept transparent$/, () => '透明的地方保持透明'],
  [/^enlarging interpolates between existing pixels/, () => '放大只是在已有像素之间插值：能满足尺寸或 dpi 要求，但不会凭空长出细节'],
  [/^JPEG has no transparency/, () => 'JPEG 不支持透明，透明处已填成白色'],
  [/^background flattened and whitened$/, () => '压平光照，把纸压白了'],
  [/^empty margins trimmed$/, () => '裁掉了空白边'],
  [/^resampled ([\d.]+)x to (\d+) x (\d+) px \(Lanczos\)$/, (m) => `按 ${m[1]} 倍重采样到 ${m[2]}×${m[3]}（Lanczos）`],
  [/^denoising \(strength ([\d.]+)\)$/, (m) => `去噪（强度 ${m[1]}）`],
  [/^sharpening \(unsharp mask, strength ([\d.]+)\)$/, (m) => `锐化（USM，强度 ${m[1]}）`],
  [/^converted to greyscale$/, () => '转成灰度'],
  [/^colour-vision simulation \((.+?)\); a preview for checking, not for publication$/, (m) => `${m[1]} 色觉模拟：只用来自查，不要拿去投稿`],
  [/^the table has (\d+) rows/, (m) => `表里有 ${m[1]} 行，大约两万行以内画图还很快`],
  [/^check: (.+)$/, (m) => `对账：${m[1]}`],
  [/^error bars are drawn as a picture/, () => '误差线是作为图形画上去的'],
  [/^procedural placeholder/, () => '这是程序生成的占位图形，不是模型画的'],
  [/^(\d+) value\(s\) are zero or negative and cannot be drawn on a log ([xy]) axis/, (m) => `有 ${m[1]} 个值是 0 或负数，${m[2] === 'y' ? '纵' : '横'}轴取对数后画不出来，这些点没有出现在图里`],
  [/^There is no column called '(.+?)' in this table, so the chart was drawn with another one; the columns are: (.+)$/, (m) => `表里没有「${m[1]}」这一列，图是用别的列画的；可用的列：${m[2]}`],
];

/** Translate one engine message for display. Unknown text comes back unchanged. */
export function say(text) {
  if (getLang() !== 'zh' || typeof text !== 'string') return text;
  for (const [pattern, make] of RULES) {
    const m = pattern.exec(text);
    if (m) return make(m);
  }
  return text;
}

export function sayAll(list) {
  return (list || []).map(say);
}
