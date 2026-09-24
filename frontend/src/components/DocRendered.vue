<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  blockIndex,
  blocksForRange,
  caretAt,
  closestBlock,
  findQuote,
  flash,
  lineLabel,
  setHighlight,
  supportsHighlights,
  textIndex,
} from '../anchors'

const props = defineProps({
  html: { type: String, required: true },
  threads: { type: Array, required: true },
  activeId: { type: Number, default: null },
  pending: { type: Object, default: null },
})
const emit = defineEmits(['activate', 'compose'])
const router = useRouter()

const wrap = ref(null)
const body = ref(null)
const markers = ref([])
const hover = ref(null)

// DOM-derived lookups, rebuilt whenever the rendered HTML changes.
let blocks = []
let index = null
const anchors = shallowRef(new Map()) // thread id -> { range, els }

// Comments from before line anchors existed have only a quote; find those by text alone.
function resolveAnchor(a) {
  if (!index || !(a?.line_start || a?.quote)) return null
  const range = findQuote(index, a.quote, a.line_start)
  if (range) return { range, els: [closestBlock(range.startContainer)].filter(Boolean) }
  if (!a.line_start) return null
  return { range: null, els: blocksForRange(blocks, a.line_start, a.line_end ?? a.line_start) }
}

function resolveAll() {
  const map = new Map()
  for (const t of props.threads) {
    const a = resolveAnchor(t)
    if (a) map.set(t.id, a)
  }
  anchors.value = map
}

function layout() {
  if (!wrap.value) return
  const base = wrap.value.getBoundingClientRect().top
  const groups = new Map()
  for (const t of props.threads) {
    const el = !t.resolved && anchors.value.get(t.id)?.els[0]
    if (!el) continue
    if (!groups.has(el)) groups.set(el, [])
    groups.get(el).push(t.id)
  }
  markers.value = [...groups].map(([el, ids]) => ({
    ids,
    top: el.getBoundingClientRect().top - base,
    line: Number(el.dataset.line),
  }))
  if (hover.value) hover.value = { ...hover.value, top: hover.value.el.getBoundingClientRect().top - base }
}

function current() {
  return props.pending ? resolveAnchor(props.pending) : anchors.value.get(props.activeId)
}

function paint() {
  const open = props.threads.filter((t) => !t.resolved).map((t) => anchors.value.get(t.id)?.range)
  setHighlight('pp-anchor', open.filter(Boolean))
  const cur = current()
  setHighlight('pp-active', cur?.range ? [cur.range] : [])
  // Whole-block highlight when there is no text range to paint (line comments,
  // text that changed since, or browsers without the Highlight API).
  body.value?.querySelectorAll('.pp-block-active').forEach((el) => el.classList.remove('pp-block-active'))
  if (cur && (!cur.range || !supportsHighlights)) cur.els.forEach((el) => el.classList.add('pp-block-active'))
}

function rebuild() {
  if (!body.value) return
  blocks = blockIndex(body.value)
  index = textIndex(body.value)
  resolveAll()
  layout()
  paint()
}

// Scrolls the passage into view; returns false if it can't be located.
function reveal(anchorOrId) {
  const a = typeof anchorOrId === 'number' ? anchors.value.get(anchorOrId) : resolveAnchor(anchorOrId)
  const el = a?.els[0]
  if (!el) return false
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  flash(el)
  return true
}

function onMouseOver(event) {
  const el = event.target.closest?.('[data-line]')
  if (!el || !body.value.contains(el) || el === hover.value?.el) return
  hover.value = {
    el,
    line_start: Number(el.dataset.line),
    line_end: Number(el.dataset.lineEnd),
    top: el.getBoundingClientRect().top - wrap.value.getBoundingClientRect().top,
  }
}

function composeOnHovered() {
  const { el, line_start, line_end } = hover.value
  const quote = el.textContent.replace(/\s+/g, ' ').trim().slice(0, 2000)
  emit('compose', { quote: quote || null, line_start, line_end })
}

function activateMarker(marker) {
  // Clicking a bubble again cycles through the threads on that block.
  const i = marker.ids.indexOf(props.activeId)
  emit('activate', marker.ids[(i + 1) % marker.ids.length])
}

function onClick(event) {
  // Links to other proposals are rendered as plain <a href="/p/...">; route them in-app.
  const href = event.target.closest('a')?.getAttribute('href')
  if (href) {
    if (href.startsWith('/p/') && !event.metaKey && !event.ctrlKey && event.button === 0) {
      event.preventDefault()
      router.push(href)
    }
    return
  }
  if (!window.getSelection()?.isCollapsed) return // end of a drag-select, not a click
  // Clicking commented (highlighted) text opens its thread; clicking elsewhere clears it.
  const caret = caretAt(event.clientX, event.clientY)
  const hit =
    caret &&
    props.threads.find((t) => {
      const range = !t.resolved && anchors.value.get(t.id)?.range
      try {
        return range && range.isPointInRange(caret.node, caret.offset)
      } catch {
        return false
      }
    })
  emit('activate', hit ? hit.id : null)
}

watch(
  () => props.html,
  async () => {
    await nextTick()
    rebuild()
  },
)
watch(() => props.threads, () => (resolveAll(), layout(), paint()), { deep: true })
watch(() => [props.activeId, props.pending], paint)

let observer
onMounted(() => {
  rebuild()
  // Re-measure when images load, fonts swap, the window resizes or the view is shown again.
  observer = new ResizeObserver(() => layout())
  observer.observe(body.value)
})
onBeforeUnmount(() => {
  observer?.disconnect()
  setHighlight('pp-anchor', [])
  setHighlight('pp-active', [])
})

defineExpose({ reveal })
</script>

<template>
  <div ref="wrap" class="doc-body" @mouseleave="hover = null">
    <div class="gutter">
      <button
        v-for="m in markers"
        :key="`${m.line}-${m.ids.join()}`"
        class="marker"
        :class="{ active: m.ids.includes(activeId) }"
        :style="{ top: `${m.top}px` }"
        :title="`${m.ids.length} open ${m.ids.length === 1 ? 'thread' : 'threads'} on line ${m.line}`"
        @click="activateMarker(m)"
      >
        <svg viewBox="0 0 20 20" aria-hidden="true">
          <path d="M3 4.5A1.5 1.5 0 0 1 4.5 3h11A1.5 1.5 0 0 1 17 4.5v8a1.5 1.5 0 0 1-1.5 1.5H8l-4 3v-3A1.5 1.5 0 0 1 3 12.5z" />
        </svg>
        {{ m.ids.length }}
      </button>
      <div v-if="hover" class="hover-gutter" :style="{ top: `${hover.top}px` }">
        <span v-if="!markers.some((m) => m.line === hover.line_start)" class="line-no">{{ hover.line_start }}</span>
        <button class="add" :title="`Comment on ${lineLabel(hover).toLowerCase()}`" @click="composeOnHovered">+</button>
      </div>
    </div>
    <div ref="body" class="markdown-body" v-html="html" @mouseover="onMouseOver" @click="onClick" />
  </div>
</template>
