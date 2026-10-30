<script setup>
import { computed, nextTick, ref } from 'vue'
import { session } from '../session'

const emit = defineEmits(['signed-in'])

const dialog = ref(null)
const input = ref(null)
const mode = ref('signin') // 'signin' or 'register'
const username = ref('')
const password = ref('')
const repeat = ref('')
const code = ref('') // the shared editor password, which is the sign-up code
const error = ref('')
const busy = ref(false)
const reason = ref('')

const registering = computed(() => mode.value === 'register')
const ready = computed(() =>
  registering.value ? username.value.trim() && password.value && repeat.value && code.value : password.value,
)

function clear() {
  password.value = repeat.value = code.value = ''
  error.value = ''
}

async function open(message = '') {
  reason.value = message
  clear()
  dialog.value.showModal()
  await nextTick()
  input.value?.focus()
}

async function setMode(next) {
  mode.value = next
  clear()
  await nextTick()
  input.value?.focus()
}

async function submit() {
  if (!ready.value) return
  if (registering.value && password.value !== repeat.value) {
    error.value = "Passwords don't match"
    return
  }
  busy.value = true
  error.value = ''
  try {
    if (registering.value) await session.register(username.value.trim(), password.value, code.value)
    else await session.signIn(username.value.trim(), password.value)
    clear()
    dialog.value.close()
    emit('signed-in')
  } catch (e) {
    error.value = e.message
  } finally {
    busy.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <dialog ref="dialog" class="login-dialog" @cancel="clear">
    <form method="dialog" @submit.prevent="submit">
      <h2>{{ registering ? 'Create an account' : 'Sign in to edit' }}</h2>
      <p class="muted small">{{ reason || 'Editing proposals requires signing in.' }}</p>
      <div class="segmented" role="tablist" aria-label="Account">
        <button type="button" role="tab" :aria-selected="!registering" :class="{ on: !registering }" @click="setMode('signin')">
          Sign in
        </button>
        <button type="button" role="tab" :aria-selected="registering" :class="{ on: registering }" @click="setMode('register')">
          Register
        </button>
      </div>
      <label class="small">
        Username
        <input
          ref="input"
          v-model="username"
          autocomplete="username"
          autocapitalize="off"
          spellcheck="false"
          maxlength="40"
          :placeholder="registering ? '3-40 letters, digits, . _ -' : 'Your username'"
        />
      </label>
      <label class="small">
        Password
        <input
          v-model="password"
          type="password"
          :autocomplete="registering ? 'new-password' : 'current-password'"
          :placeholder="registering ? 'At least 8 characters' : ''"
        />
      </label>
      <template v-if="registering">
        <label class="small">
          Repeat password
          <input v-model="repeat" type="password" autocomplete="new-password" />
        </label>
        <label class="small">
          Sign-up code
          <input v-model="code" type="password" autocomplete="off" placeholder="The editor password" />
        </label>
        <p class="muted small">Ask a teammate for the editor password; it's needed once, to create your account.</p>
      </template>
      <p v-else class="muted small">No account? Register one, or leave the username empty to use the shared editor password.</p>
      <p v-if="error" class="notice error small">{{ error }}</p>
      <div class="form-actions end">
        <button type="button" class="btn" @click="dialog.close()">Cancel</button>
        <button class="btn btn-primary" :disabled="busy || !ready">
          {{ busy ? 'Checking...' : registering ? 'Create account' : 'Sign in' }}
        </button>
      </div>
    </form>
  </dialog>
</template>
