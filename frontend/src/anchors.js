// Inline comments are anchored by the source lines they came from plus the
// quoted text. Rendered blocks carry data-line / data-line-end (markdown.js) and
// so do the lines of the source view, so these helpers serve both views.

const strip = (s) => s.replace(/\s+/g, '')

export const supportsHighlights = typeof CSS !== 'undefined' && 'highlights' in CSS && typeof Highlight !== 'undefined'

export function setHighlight(name, ranges) {
  if (!supportsHighlights) return
  if (ranges.length) CSS.highlights.set(name, new Highlight(...ranges))
  else CSS.highlights.delete(name)
}

export function closestBlock(node) {
  const el = node?.nodeType === Node.ELEMENT_NODE ? node : node?.parentElement
  return el?.closest('[data-line]') ?? null
}

export function lineLabel({ line_start, line_end }) {
  return line_end && line_end !== line_start ? `Lines ${line_start}–${line_end}` : `Line ${line_start}`
}

export function blockIndex(root) {
  return [...root.querySelectorAll('[data-line]')].map((el) => ({
    el,
    start: Number(el.dataset.line),
    end: Number(el.dataset.lineEnd),
  }))
}

// Deepest block containing line n. Descendants follow their ancestors in document
// order, so the last match is the innermost. Falls back to the nearest block
// before n (e.g. n is a blank line, or the file got shorter).
export function blockForLine(blocks, n) {
  let containing = null
  let before = null
  for (const b of blocks) {
    if (b.start <= n && n <= b.end) containing = b
    if (b.start <= n) before = b
  }
  return containing ?? before
}

export function blocksForRange(blocks, start, end) {
  const found = new Set()
  for (let n = start; n <= end; n++) {
    const b = blockForLine(blocks, n)
    if (b) found.add(b.el)
  }
  return [...found]
}

// All non-whitespace characters under root, with a pointer back to the text node
// and offset each came from. Matching ignores whitespace because selection text
// and DOM text disagree on it (newlines between blocks, tabs between table cells).
export function textIndex(root) {
  const chars = []
  const nodes = []
  const offsets = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const data = node.data
    for (let i = 0; i < data.length; i++) {
      if (/\s/.test(data[i])) continue
      chars.push(data[i])
      nodes.push(node)
      offsets.push(i)
    }
  }
  return { text: chars.join(''), nodes, offsets }
}

// Range for the occurrence of quote closest to nearLine, or null if the text is
// no longer in the document.
export function findQuote(index, quote, nearLine) {
  const needle = strip(quote || '')
  if (!needle) return null
  let best = null
  let bestDistance = Infinity
  let at = index.text.indexOf(needle)
  for (let tries = 0; at !== -1 && tries < 200; tries++) {
    const line = Number(closestBlock(index.nodes[at])?.dataset.line)
    const distance = nearLine && line ? Math.abs(line - nearLine) : 0
    if (distance < bestDistance) {
      const last = at + needle.length - 1
      best = document.createRange()
      best.setStart(index.nodes[at], index.offsets[at])
      best.setEnd(index.nodes[last], index.offsets[last] + 1)
      bestDistance = distance
      if (distance === 0) break
    }
    at = index.text.indexOf(needle, at + 1)
  }
  return best
}

export function quoteFound(haystacks, quote) {
  const needle = strip(quote || '')
  return !needle || haystacks.some((h) => h.includes(needle))
}

export { strip as stripWhitespace }

// Text nodes the range actually covers, skipping ones touched only at a boundary
// (a triple-click selection ends at offset 0 of the *next* paragraph).
function selectedTextNodes(root, range) {
  const nodes = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!range.intersectsNode(n) || !n.data.trim()) continue
    if (n === range.endContainer && range.endOffset === 0) continue
    if (n === range.startContainer && range.startOffset >= n.data.length) continue
    nodes.push(n)
  }
  return nodes
}

export function anchorFromSelection(root, selection) {
  if (!root || !selection || selection.isCollapsed || !selection.rangeCount) return null
  const range = selection.getRangeAt(0)
  if (!root.contains(range.commonAncestorContainer)) return null
  const quote = selection.toString().trim()
  if (!quote) return null
  const nodes = selectedTextNodes(root, range)
  const first = closestBlock(nodes[0])
  const last = closestBlock(nodes[nodes.length - 1])
  if (!first || !last) return null
  const line_start = Number(first.dataset.line)
  return {
    quote: quote.slice(0, 2000),
    line_start,
    line_end: Math.max(line_start, Number(last.dataset.lineEnd)),
  }
}

export function caretAt(x, y) {
  if (document.caretPositionFromPoint) {
    const p = document.caretPositionFromPoint(x, y)
    return p && { node: p.offsetNode, offset: p.offset }
  }
  if (document.caretRangeFromPoint) {
    const r = document.caretRangeFromPoint(x, y)
    return r && { node: r.startContainer, offset: r.startOffset }
  }
  return null
}

export function flash(el) {
  if (!el) return
  el.classList.remove('pp-flash')
  void el.offsetWidth // restart the animation
  el.classList.add('pp-flash')
  setTimeout(() => el.classList.remove('pp-flash'), 1300)
}
