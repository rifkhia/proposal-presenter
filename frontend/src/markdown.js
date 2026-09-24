import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import { encodePath } from './api'

const md = new MarkdownIt({ html: true, linkify: true, typographer: true })

// Anything with a scheme, protocol-relative, root-absolute or a pure #anchor is left untouched.
const isAbsolute = (url) => /^([a-z][a-z0-9+.-]*:|\/|#)/i.test(url)

// Resolve "../img/a.png" against the proposal's folder, e.g. "team" -> "img/a.png".
function resolveRelative(baseDir, url) {
  const cut = url.search(/[?#]/)
  const pathPart = cut === -1 ? url : url.slice(0, cut)
  const suffix = cut === -1 ? '' : url.slice(cut)
  const parts = baseDir ? baseDir.split('/') : []
  for (const seg of pathPart.split('/')) {
    if (seg === '..') parts.pop()
    else if (seg && seg !== '.') parts.push(seg)
  }
  return { path: parts.join('/'), suffix }
}

function slugify(text) {
  return (
    text
      .toLowerCase()
      .trim()
      .replace(/[^\p{L}\p{N}\s-]/gu, '')
      .replace(/\s+/g, '-') || 'section'
  )
}

// Give headings ids so "#section" links and deep links work.
md.core.ruler.push('heading_ids', (state) => {
  const seen = new Map()
  const tokens = state.tokens
  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i].type !== 'heading_open') continue
    const base = slugify(tokens[i + 1].content)
    const n = seen.get(base) || 0
    seen.set(base, n + 1)
    tokens[i].attrSet('id', n ? `${base}-${n}` : base)
  }
})

// Tag every rendered block with the source lines it came from (1-based,
// inclusive), so inline comments can be anchored to "line 12" and found again.
md.core.ruler.push('source_lines', (state) => {
  const src = state.src.split('\n')
  for (const token of state.tokens) {
    if (!token.map || token.nesting < 0 || token.hidden || token.type === 'inline') continue
    const start = token.map[0] + 1
    let end = token.map[1]
    while (end > start && !src[end - 1]?.trim()) end-- // markdown-it includes trailing blank lines
    token.attrSet('data-line', String(start))
    token.attrSet('data-line-end', String(end))
  }
})

const defaultImage = md.renderer.rules.image
md.renderer.rules.image = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const src = token.attrGet('src')
  if (src && !isAbsolute(src)) {
    const { path, suffix } = resolveRelative(env.baseDir, src)
    token.attrSet('src', `/api/assets/${encodePath(path)}${suffix}`)
  }
  token.attrSet('loading', 'lazy')
  return defaultImage(tokens, idx, options, env, self)
}

const defaultLinkOpen =
  md.renderer.rules.link_open || ((tokens, idx, options, env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const token = tokens[idx]
  const href = token.attrGet('href') || ''
  if (/^https?:\/\//i.test(href)) {
    token.attrSet('target', '_blank')
    token.attrSet('rel', 'noopener noreferrer')
  } else if (href && !isAbsolute(href)) {
    const { path, suffix } = resolveRelative(env.baseDir, href)
    // Links to other proposals stay in the app; anything else is served as a file.
    token.attrSet(
      'href',
      /\.md$/i.test(path) ? `/p/${encodePath(path)}${suffix}` : `/api/assets/${encodePath(path)}${suffix}`,
    )
  }
  return defaultLinkOpen(tokens, idx, options, env, self)
}

export function renderMarkdown(source, proposalPath) {
  const baseDir = proposalPath.includes('/') ? proposalPath.slice(0, proposalPath.lastIndexOf('/')) : ''
  const html = md.render(source, { baseDir })
  return DOMPurify.sanitize(html, { ADD_ATTR: ['target'] })
}
