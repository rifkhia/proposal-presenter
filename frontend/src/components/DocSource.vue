<script setup>
import { computed, nextTick, ref } from 'vue'
import { flash } from '../anchors'

const props = defineProps({
  content: { type: String, required: true },
  threads: { type: Array, required: true },
  activeId: { type: Number, default: null },
  pending: { type: Object, default: null },
})
const emit = defineEmits(['activate', 'compose'])

const root = ref(null)
const lines = computed(() => props.content.replace(/\n$/, '').split('\n'))
let lastClicked = null

const current = computed(() => props.pending ?? props.threads.find((t) => t.id === props.activeId) ?? null)

const openThreads = computed(() => props.threads.filter((t) => !t.resolved && t.line_start))

// line -> ids of open threads starting there (the bubble), and every line any open thread covers.
const markers = computed(() => {
  const map = new Map()
  for (const t of openThreads.value) {
    if (!map.has(t.line_start)) map.set(t.line_start, [])
    map.get(t.line_start).push(t.id)
  }
  return map
})
const commented = computed(() => {
  const set = new Set()
  for (const t of openThreads.value) for (let n = t.line_start; n <= (t.line_end ?? t.line_start); n++) set.add(n)
  return set
})

function isCurrent(n) {
  const c = current.value
  return c?.line_start && n >= c.line_start && n <= (c.line_end ?? c.line_start)
}

// Click a line number to comment on it; shift-click to extend from the last one.
function onLineClick(n, event) {
  const [start, end] = event.shiftKey && lastClicked ? [Math.min(lastClicked, n), Math.max(lastClicked, n)] : [n, n]
  lastClicked = n
  const quote = lines.value.slice(start - 1, end).join('\n').trim().slice(0, 2000)
  emit('compose', { quote: quote || null, line_start: start, line_end: end })
}

function activateMarker(ids) {
  const i = ids.indexOf(props.activeId)
  emit('activate', ids[(i + 1) % ids.length])
}

async function reveal(anchorOrId) {
  const a = typeof anchorOrId === 'number' ? props.threads.find((t) => t.id === anchorOrId) : anchorOrId
  await nextTick()
  const el = a?.line_start && root.value?.querySelector(`[data-line="${Math.min(a.line_start, lines.value.length)}"]`)
  if (!el) return false
  el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  flash(el)
  return true
}

defineExpose({ reveal })
</script>

<template>
  <div ref="root" class="source" role="table" aria-label="Proposal source">
    <div
      v-for="(text, i) in lines"
      :key="i"
      class="src-line"
      :class="{ current: isCurrent(i + 1), commented: commented.has(i + 1) }"
      :data-line="i + 1"
      :data-line-end="i + 1"
      role="row"
    >
      <span class="src-marker">
        <button
          v-if="markers.has(i + 1)"
          class="marker"
          :class="{ active: markers.get(i + 1).includes(activeId) }"
          :title="`${markers.get(i + 1).length} open on line ${i + 1}`"
          @click="activateMarker(markers.get(i + 1))"
        >
          {{ markers.get(i + 1).length }}
        </button>
      </span>
      <button class="src-ln" :title="`Comment on line ${i + 1} (shift-click for a range)`" @click="onLineClick(i + 1, $event)">
        {{ i + 1 }}
      </button>
      <span class="src-code">{{ text }}</span>
    </div>
  </div>
</template>
