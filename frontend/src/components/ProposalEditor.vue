<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { EditorState, RangeSetBuilder, StateEffect, StateField } from '@codemirror/state'
import {
  Decoration,
  EditorView,
  GutterMarker,
  drawSelection,
  gutter,
  highlightActiveLine,
  highlightActiveLineGutter,
  keymap,
  lineNumbers,
} from '@codemirror/view'
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands'
import { HighlightStyle, syntaxHighlighting } from '@codemirror/language'
import { markdown } from '@codemirror/lang-markdown'
import { search, searchKeymap } from '@codemirror/search'
import { tags } from '@lezer/highlight'

const props = defineProps({
  content: { type: String, required: true },
  threads: { type: Array, required: true },
  activeId: { type: Number, default: null },
})
const emit = defineEmits(['activate', 'dirty', 'save', 'lines'])

const host = ref(null)
let view = null

// ---- Comment anchors that follow the text while you type ---------------------------
// Each open inline thread becomes a { from, to } range in the document. Every edit maps
// the ranges through the change, so markers stay on the commented text; a range an edit
// touched is flagged `edited` (the thread may be outdated once saved).

const setActive = StateEffect.define()
const refreshThreads = StateEffect.define() // Map id -> title, for threads still open

const summarize = (t) => {
  const replies = t.replies.length ? ` (+${t.replies.length} ${t.replies.length === 1 ? 'reply' : 'replies'})` : ''
  const text = `${t.author}: ${t.body}`
  return (text.length > 220 ? `${text.slice(0, 217)}...` : text) + replies
}

function initialAnchors(doc, threads) {
  return threads
    .filter((t) => !t.resolved && t.line_start)
    .map((t) => {
      const start = Math.min(t.line_start, doc.lines)
      const end = Math.min(Math.max(t.line_end ?? t.line_start, start), doc.lines)
      return { id: t.id, from: doc.line(start).from, to: doc.line(end).to, edited: false, title: summarize(t) }
    })
}

const anchorsField = StateField.define({
  create: () => ({ list: [], active: null }),
  update(value, tr) {
    let { list, active } = value
    if (tr.docChanged) {
      list = list.map((a) => {
        const from = tr.changes.mapPos(a.from, 1)
        const to = Math.max(from, tr.changes.mapPos(a.to, -1))
        return { ...a, from, to, edited: a.edited || tr.changes.touchesRange(a.from, a.to) !== false }
      })
    }
    for (const e of tr.effects) {
      if (e.is(setActive)) active = e.value
      if (e.is(refreshThreads)) {
        list = list.filter((a) => e.value.has(a.id)).map((a) => ({ ...a, title: e.value.get(a.id) }))
      }
    }
    return { list, active }
  },
})

const lineOf = (state, pos) => state.doc.lineAt(pos)

// Where each thread's lines are right now in the (unsaved) text, for the panel chips.
function currentLines(state) {
  const lines = new Map()
  for (const a of state.field(anchorsField).list) {
    lines.set(a.id, { line_start: lineOf(state, a.from).number, line_end: lineOf(state, a.to).number })
  }
  return lines
}

const commentedLines = EditorView.decorations.compute([anchorsField], (state) => {
  const { list, active } = state.field(anchorsField)
  const classes = new Map() // line start -> Set of classes
  for (const a of list) {
    const first = lineOf(state, a.from).number
    const last = lineOf(state, a.to).number
    for (let n = first; n <= last; n++) {
      const pos = state.doc.line(n).from
      if (!classes.has(pos)) classes.set(pos, new Set(['cm-commented']))
      if (a.id === active) classes.get(pos).add('cm-commented-active')
      if (a.edited) classes.get(pos).add('cm-commented-edited')
    }
  }
  const builder = new RangeSetBuilder()
  for (const pos of [...classes.keys()].sort((x, y) => x - y)) {
    builder.add(pos, pos, Decoration.line({ class: [...classes.get(pos)].join(' ') }))
  }
  return builder.finish()
})

class ThreadMarker extends GutterMarker {
  constructor(anchors, active) {
    super()
    this.anchors = anchors
    this.active = active
  }
  eq(other) {
    return (
      other.active === this.active &&
      other.anchors.length === this.anchors.length &&
      other.anchors.every((a, i) => a.id === this.anchors[i].id && a.edited === this.anchors[i].edited && a.title === this.anchors[i].title)
    )
  }
  toDOM() {
    const edited = this.anchors.some((a) => a.edited)
    const el = document.createElement('span')
    el.className = `cm-thread-marker${this.active ? ' active' : ''}${edited ? ' edited' : ''}`
    el.textContent = String(this.anchors.length)
    el.title =
      this.anchors.map((a) => a.title).join('\n\n') +
      (edited ? '\n\n(You changed this since it was commented; it may be outdated after saving.)' : '') +
      '\n\nClick to show in the comments panel.'
    return el
  }
}

function markersAt(state, lineFrom) {
  return state.field(anchorsField).list.filter((a) => lineOf(state, a.from).from === lineFrom)
}

const threadGutter = gutter({
  class: 'cm-thread-gutter',
  markers(v) {
    const { list, active } = v.state.field(anchorsField)
    const starts = [...new Set(list.map((a) => lineOf(v.state, a.from).from))].sort((x, y) => x - y)
    const builder = new RangeSetBuilder()
    for (const pos of starts) {
      const here = markersAt(v.state, pos)
      builder.add(pos, pos, new ThreadMarker(here, here.some((a) => a.id === active)))
    }
    return builder.finish()
  },
  initialSpacer: () => new ThreadMarker([{ id: 0, edited: false, title: '' }, { id: 1, edited: false, title: '' }], false),
  domEventHandlers: {
    click(v, line) {
      const ids = markersAt(v.state, line.from).map((a) => a.id)
      if (!ids.length) return false
      const i = ids.indexOf(v.state.field(anchorsField).active)
      emit('activate', ids[(i + 1) % ids.length])
      return true
    },
  },
})

// ---- Look ----------------------------------------------------------------------------

const theme = EditorView.theme({
  '&': {
    height: '100%',
    backgroundColor: 'var(--surface)',
    color: 'var(--text)',
    fontSize: '14px',
  },
  '&.cm-focused': { outline: 'none' },
  '.cm-scroller': { fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', lineHeight: '1.6' },
  '.cm-content': { caretColor: 'var(--text)', padding: '10px 0' },
  '.cm-line': { padding: '0 14px' },
  '.cm-gutters': { backgroundColor: 'var(--surface-2)', color: 'var(--text-muted)', borderRight: '1px solid var(--border)' },
  '.cm-activeLine': { backgroundColor: 'color-mix(in srgb, var(--accent) 5%, transparent)' },
  '.cm-activeLineGutter': { backgroundColor: 'color-mix(in srgb, var(--accent) 10%, transparent)', color: 'var(--text)' },
  '.cm-cursor': { borderLeftColor: 'var(--text)' },
  '&.cm-focused .cm-selectionBackground, .cm-selectionBackground': { backgroundColor: 'color-mix(in srgb, var(--accent) 22%, transparent) !important' },
  '.cm-panels': { backgroundColor: 'var(--surface-2)', color: 'var(--text)', borderColor: 'var(--border)' },
})

const markdownStyle = HighlightStyle.define([
  { tag: tags.heading, fontWeight: '700', color: 'var(--accent)' },
  { tag: tags.strong, fontWeight: '700' },
  { tag: tags.emphasis, fontStyle: 'italic' },
  { tag: tags.strikethrough, textDecoration: 'line-through' },
  { tag: tags.link, color: 'var(--accent)' },
  { tag: tags.url, color: 'var(--text-muted)', textDecoration: 'underline' },
  { tag: tags.monospace, color: 'var(--quote)' },
  { tag: tags.quote, color: 'var(--text-muted)', fontStyle: 'italic' },
  { tag: [tags.processingInstruction, tags.contentSeparator, tags.meta], color: 'var(--text-muted)' },
])

// ---- Lifecycle -----------------------------------------------------------------------

onMounted(() => {
  view = new EditorView({
    parent: host.value,
    state: EditorState.create({
      doc: props.content,
      extensions: [
        threadGutter,
        lineNumbers(),
        highlightActiveLineGutter(),
        history(),
        drawSelection(),
        highlightActiveLine(),
        EditorView.lineWrapping,
        markdown(),
        syntaxHighlighting(markdownStyle),
        search({ top: true }),
        keymap.of([
          { key: 'Mod-s', preventDefault: true, run: () => (emit('save'), true) },
          ...defaultKeymap,
          ...historyKeymap,
          ...searchKeymap,
        ]),
        anchorsField.init((state) => ({ list: initialAnchors(state.doc, props.threads), active: props.activeId })),
        commentedLines,
        theme,
        EditorView.updateListener.of((u) => {
          if (!u.docChanged) return
          emit('dirty', u.state.doc.toString() !== props.content)
          emit('lines', currentLines(u.state))
        }),
      ],
    }),
  })
  view.focus()
})

onBeforeUnmount(() => view?.destroy())

watch(
  () => props.activeId,
  (id) => view?.dispatch({ effects: setActive.of(id) }),
)

// Resolving a thread or replying while editing: drop resolved ones, refresh tooltips.
watch(
  () => props.threads,
  (threads) => {
    const open = new Map(threads.filter((t) => !t.resolved).map((t) => [t.id, summarize(t)]))
    view?.dispatch({ effects: refreshThreads.of(open) })
  },
  { deep: true },
)

function getContent() {
  return view.state.doc.toString()
}

// Scroll to a thread's (current, mapped) lines and put the cursor there.
function reveal(id) {
  const a = view?.state.field(anchorsField).list.find((x) => x.id === id)
  if (!a) return false
  view.dispatch({
    selection: { anchor: a.from },
    effects: [setActive.of(id), EditorView.scrollIntoView(a.from, { y: 'center' })],
  })
  view.focus()
  return true
}

defineExpose({ getContent, reveal })
</script>

<template>
  <div ref="host" class="editor-host" />
</template>
