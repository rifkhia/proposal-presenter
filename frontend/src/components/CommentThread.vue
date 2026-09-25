<script setup>
import { computed, nextTick, ref } from 'vue'
import { author } from '../author'
import { lineLabel } from '../anchors'
import { fullDate, timeAgo } from '../format'
import CommentItem from './CommentItem.vue'

const props = defineProps({
  thread: { type: Object, required: true },
  store: { type: Object, required: true },
  active: { type: Boolean, default: false },
  outdated: { type: Boolean, default: false },
  // While editing: where the thread's lines are in the unsaved text.
  live: { type: Object, default: null },
  // A callback rather than an event: reopening moves the thread off the Resolved
  // list, which unmounts this component, and Vue drops events from unmounted ones.
  onReopened: { type: Function, default: null },
})
const emit = defineEmits(['activate', 'need-name'])

const moved = computed(
  () => props.live && (props.live.line_start !== props.thread.line_start || props.live.line_end !== props.thread.line_end),
)
const wasLabel = computed(() => lineLabel(props.thread).replace(/^Lines? /, 'was '))

const replying = ref(false)
const replyBody = ref('')
const busy = ref(false)
const error = ref('')
const replyBox = ref(null)
const copied = ref(false)

function haveName() {
  if (author.value.trim()) return true
  emit('need-name')
  return false
}

async function run(action) {
  busy.value = true
  error.value = ''
  try {
    await action()
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function startReply() {
  replying.value = true
  await nextTick()
  replyBox.value?.focus()
}

function sendReply() {
  if (!replyBody.value.trim() || !haveName()) return
  run(async () => {
    await props.store.reply(props.thread, { author: author.value, body: replyBody.value })
    replyBody.value = ''
    replying.value = false
  })
}

function toggleResolved() {
  if (!props.thread.resolved && !haveName()) return
  run(async () => {
    await props.store.setResolved(props.thread, !props.thread.resolved, author.value.trim())
    if (!props.thread.resolved) props.onReopened?.(props.thread.id)
  })
}

function remove(comment) {
  const replies = comment === props.thread ? props.thread.replies.length : 0
  const what = replies ? `this thread and its ${replies} ${replies === 1 ? 'reply' : 'replies'}` : `this comment by ${comment.author}`
  if (confirm(`Delete ${what}?`)) run(() => props.store.remove(comment, props.thread))
}

async function copyLink() {
  const url = new URL(window.location.href)
  url.searchParams.set('thread', props.thread.id)
  try {
    await navigator.clipboard.writeText(url.toString())
    copied.value = true
    setTimeout(() => (copied.value = false), 1500)
  } catch {
    window.prompt('Copy this link:', url.toString())
  }
}

function onKeydown(event) {
  if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) sendReply()
  if (event.key === 'Escape') replying.value = false
}
</script>

<template>
  <article class="thread" :class="{ active, resolved: thread.resolved }" :data-thread="thread.id">
    <div v-if="thread.line_start" class="thread-anchor">
      <button
        class="anchor-chip"
        :title="outdated ? 'The proposal changed since; showing the original line' : 'Show in the proposal'"
        @click="emit('activate', thread.id)"
      >
        <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M2 3h12M2 8h12M2 13h7" /></svg>
        {{ lineLabel(moved ? live : thread) }}
        <span v-if="moved" class="was">({{ wasLabel }})</span>
      </button>
      <span v-if="outdated" class="badge outdated">Outdated</span>
      <span v-if="thread.resolved" class="badge resolved-badge">Resolved</span>
    </div>
    <span v-else-if="thread.resolved" class="badge resolved-badge">Resolved</span>

    <blockquote v-if="thread.quote" class="comment-quote clickable" @click="emit('activate', thread.id)">
      {{ thread.quote }}
    </blockquote>

    <CommentItem :comment="thread" @delete="remove(thread)" />

    <ol v-if="thread.replies.length" class="replies">
      <li v-for="r in thread.replies" :key="r.id">
        <CommentItem :comment="r" @delete="remove(r)" />
      </li>
    </ol>

    <p v-if="thread.resolved" class="resolved-note">
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3 3 7-7" /></svg>
      Resolved{{ thread.resolved_by ? ` by ${thread.resolved_by}` : '' }}
      <span v-if="thread.resolved_at" class="muted" :title="fullDate(thread.resolved_at)">· {{ timeAgo(thread.resolved_at) }}</span>
    </p>

    <form v-if="replying" class="reply-form" @submit.prevent="sendReply">
      <textarea
        ref="replyBox"
        v-model="replyBody"
        rows="2"
        maxlength="5000"
        placeholder="Write a reply..."
        aria-label="Reply"
        @keydown="onKeydown"
      />
      <div class="form-actions">
        <button type="button" class="btn btn-sm" @click="replying = false">Cancel</button>
        <button class="btn btn-sm btn-primary" :disabled="busy || !replyBody.trim()">Reply</button>
      </div>
    </form>
    <div v-else class="thread-actions">
      <button class="btn btn-sm" @click="startReply">Reply</button>
      <button class="btn btn-sm" :disabled="busy" @click="toggleResolved">
        {{ thread.resolved ? 'Reopen' : 'Resolve' }}
      </button>
      <button class="link-btn" @click="copyLink">{{ copied ? 'Link copied' : 'Copy link' }}</button>
    </div>
    <p v-if="error" class="notice error small">{{ error }}</p>
  </article>
</template>
