import { computed, reactive, ref, watch } from 'vue'
import { api } from './api'

// Threads sit in document order: inline ones by line, general comments after.
function byPosition(a, b) {
  const la = a.line_start ?? Infinity
  const lb = b.line_start ?? Infinity
  return la - lb || a.created_at.localeCompare(b.created_at) || a.id - b.id
}

export function useComments(path) {
  const threads = ref([])
  const loading = ref(true)
  const error = ref('')

  async function load() {
    loading.value = true
    error.value = ''
    try {
      threads.value = await api.listComments(path.value)
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  const sorted = computed(() => [...threads.value].sort(byPosition))
  const open = computed(() => sorted.value.filter((t) => !t.resolved))
  const resolved = computed(() => sorted.value.filter((t) => t.resolved))
  const find = (id) => threads.value.find((t) => t.id === id)

  async function addThread({ author, body, anchor }) {
    const created = await api.addComment({
      proposal: path.value,
      author,
      body,
      quote: anchor?.quote || null,
      line_start: anchor?.line_start ?? null,
      line_end: anchor?.line_end ?? null,
      version: anchor?.version ?? null,
    })
    threads.value.push(created)
    return created
  }

  async function reply(thread, { author, body }) {
    const created = await api.addComment({ proposal: path.value, author, body, parent_id: thread.id })
    thread.replies.push(created)
    return created
  }

  async function setResolved(thread, resolved, by) {
    Object.assign(thread, await api.resolveComment(thread.id, resolved, by || null))
  }

  async function remove(comment, thread) {
    await api.deleteComment(comment.id)
    if (thread && thread.id !== comment.id) {
      thread.replies = thread.replies.filter((r) => r.id !== comment.id)
    } else {
      threads.value = threads.value.filter((t) => t.id !== comment.id)
    }
  }

  watch(path, load, { immediate: true })

  // reactive() unwraps the refs, so components can use store.threads etc. directly.
  return reactive({ threads, sorted, open, resolved, loading, error, find, load, addThread, reply, setResolved, remove })
}
