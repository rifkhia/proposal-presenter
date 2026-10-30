<script setup>
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, encodePath } from '../api'
import { isClaudeUrl } from '../markdown'
import { session } from '../session'

defineProps({ folders: { type: Array, default: () => [] } })
const emit = defineEmits(['need-sign-in'])

const NOT_EMBEDDABLE =
  "> Claude doesn't allow artifacts to be embedded in other sites. To show the artifact here, download its HTML in Claude and upload it."

const router = useRouter()
const dialog = ref(null)
const fileInput = ref(null)
const nameInput = ref(null)
const mode = ref('file') // 'file' or 'link' (a Claude artifact link, saved as a small .md)
const filename = ref('')
const nameEdited = ref(false) // in link mode the name follows the title until edited
const folder = ref('') // empty = the top-level folder
const fileText = ref(null) // text of the chosen file
const url = ref('')
const title = ref('')
const description = ref('')
const error = ref('')
const busy = ref(false)
const existing = ref(null) // the 409's { path, version } when the name is taken

const slug = (text) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .slice(0, 80)
    .replace(/^-+|-+$/g, '') || 'artifact'

// The parsed URL in <...> form, so text like "x) [other](https://..." can't add a second link.
const linkMarkdown = computed(() => {
  let href
  try {
    href = new URL(url.value.trim()).href
  } catch {
    return '' // not a URL yet; submit() refuses it before this is used
  }
  return (
    [`# ${title.value.trim()}`, description.value.trim(), `[Open the artifact in Claude](<${href}>)`, NOT_EMBEDDABLE]
      .filter(Boolean)
      .join('\n\n') + '\n'
  )
})
const content = computed(() => (mode.value === 'file' ? fileText.value : linkMarkdown.value))
const ready = computed(
  () =>
    filename.value.trim() &&
    (mode.value === 'file' ? fileText.value !== null : url.value.trim() && title.value.trim()),
)

function reset() {
  filename.value = ''
  nameEdited.value = false
  fileText.value = null
  url.value = ''
  title.value = ''
  description.value = ''
  error.value = ''
  existing.value = null
  if (fileInput.value) fileInput.value.value = ''
}

function open() {
  reset()
  folder.value = ''
  mode.value = 'file'
  dialog.value.showModal()
}

function setMode(m) {
  reset()
  mode.value = m
}

async function onFile(e) {
  const f = e.target.files[0]
  fileText.value = null
  existing.value = null
  error.value = ''
  if (!f) return
  if (f.size > 2_000_000) {
    error.value = 'File is larger than 2 MB'
    return
  }
  fileText.value = await f.text()
  filename.value = f.name
}

function onTitle() {
  existing.value = null
  if (!nameEdited.value) filename.value = `${slug(title.value)}.md`
}

function onName() {
  existing.value = null
  nameEdited.value = true
}

function finish(path) {
  dialog.value.close()
  router.push(`/p/${encodePath(path)}`)
}

// The session expired: the list signs in again and then calls submit() once more.
function needSignIn() {
  session.signedIn = false
  emit('need-sign-in')
}

async function submit() {
  if (busy.value || !ready.value) return
  if (mode.value === 'link' && !(/^https:\/\//i.test(url.value.trim()) && isClaudeUrl(url.value.trim()))) {
    error.value = 'Use an https:// link on claude.ai, claude.site or claude.com'
    return
  }
  // Forgive stray spaces and slashes here; the server rejects them.
  let name = filename.value.trim()
  const dir = folder.value.trim().replace(/^\/+|\/+$/g, '')
  // A link is saved as Markdown, never under an HTML name.
  if (mode.value === 'link' && !/\.md$/i.test(name)) {
    if (/\.html?$/i.test(name)) {
      error.value = 'A link is saved as Markdown: use a .md file name'
      return
    }
    name += '.md'
  }
  busy.value = true
  error.value = ''
  existing.value = null
  try {
    const res = await api.uploadProposal({ filename: name, folder: dir, content: content.value })
    finish(res.path)
  } catch (e) {
    if (e.status === 401) needSignIn()
    else if (e.status === 409 && e.data?.version) existing.value = e.data
    else error.value = e.message
  } finally {
    busy.value = false
  }
}

// Replacing is a normal save of the existing file, so comments follow the new text.
async function replace() {
  busy.value = true
  error.value = ''
  try {
    const res = await api.saveProposal(existing.value.path, content.value, existing.value.version)
    finish(res.proposal.path)
  } catch (e) {
    if (e.status === 401) return needSignIn()
    if (e.status === 409) existing.value = null
    error.value = e.message
  } finally {
    busy.value = false
  }
}

async function rename() {
  existing.value = null
  await nextTick()
  nameInput.value?.focus()
}

defineExpose({ open, submit })
</script>

<template>
  <dialog ref="dialog" class="login-dialog">
    <form method="dialog" @submit.prevent="submit">
      <h2>Upload a proposal</h2>
      <div class="segmented" role="tablist" aria-label="Upload">
        <button type="button" role="tab" :aria-selected="mode === 'file'" :class="{ on: mode === 'file' }" @click="setMode('file')">
          File
        </button>
        <button type="button" role="tab" :aria-selected="mode === 'link'" :class="{ on: mode === 'link' }" @click="setMode('link')">
          Claude artifact link
        </button>
      </div>

      <template v-if="mode === 'file'">
        <p class="muted small">
          Markdown (<code>.md</code>) or HTML (<code>.html</code>, e.g. a Claude artifact's download), up to 2 MB.
        </p>
        <input
          ref="fileInput"
          type="file"
          accept=".md,.html,.htm,text/markdown,text/html"
          aria-label="Proposal file"
          @change="onFile"
        />
      </template>
      <template v-else>
        <p class="muted small">Adds a proposal that links to the artifact. Claude doesn't allow showing it here.</p>
        <label class="small">
          Link
          <input v-model="url" type="url" placeholder="https://claude.ai/public/artifacts/..." @input="existing = null" />
        </label>
        <label class="small">
          Title
          <input v-model="title" placeholder="Pricing calculator" @input="onTitle" />
        </label>
        <label class="small">
          Description (optional)
          <textarea v-model="description" rows="3" @input="existing = null" />
        </label>
      </template>

      <label class="small">
        File name
        <input ref="nameInput" v-model="filename" placeholder="my-proposal.md" @input="onName" />
      </label>
      <label class="small">
        Folder
        <input v-model="folder" list="upload-folders" placeholder="Top level" @input="existing = null" />
        <datalist id="upload-folders">
          <option v-for="f in folders" :key="f" :value="f" />
        </datalist>
      </label>
      <div v-if="existing" class="notice error small">
        A proposal with this name exists. Replace it (comments will follow the new text), or rename yours?
        <div class="conflict-actions">
          <button type="button" class="btn btn-sm btn-danger" :disabled="busy" @click="replace">Replace it</button>
          <button type="button" class="btn btn-sm" @click="rename">Rename</button>
        </div>
      </div>
      <p v-if="error" class="notice error small">{{ error }}</p>
      <div class="form-actions end">
        <button type="button" class="btn" @click="dialog.close()">Cancel</button>
        <button class="btn btn-primary" :disabled="busy || !ready || !!existing">
          {{ busy ? 'Uploading...' : 'Upload' }}
        </button>
      </div>
    </form>
  </dialog>
</template>
