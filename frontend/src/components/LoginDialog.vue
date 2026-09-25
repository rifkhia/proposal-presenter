<script setup>
import { nextTick, ref } from 'vue'
import { session } from '../session'

const emit = defineEmits(['signed-in'])

const dialog = ref(null)
const input = ref(null)
const password = ref('')
const error = ref('')
const busy = ref(false)
const reason = ref('')

async function open(message = '') {
  reason.value = message
  error.value = ''
  password.value = ''
  dialog.value.showModal()
  await nextTick()
  input.value?.focus()
}

async function submit() {
  if (!password.value) return
  busy.value = true
  error.value = ''
  try {
    await session.signIn(password.value)
    password.value = ''
    dialog.value.close()
    emit('signed-in')
  } catch (e) {
    error.value = e.message
    input.value?.select()
  } finally {
    busy.value = false
  }
}

defineExpose({ open })
</script>

<template>
  <dialog ref="dialog" class="login-dialog" @cancel="password = ''">
    <form method="dialog" @submit.prevent="submit">
      <h2>Sign in to edit</h2>
      <p class="muted small">{{ reason || 'Editing proposals requires the editor password.' }}</p>
      <input
        ref="input"
        v-model="password"
        type="password"
        autocomplete="current-password"
        placeholder="Editor password"
        aria-label="Editor password"
      />
      <p v-if="error" class="notice error small">{{ error }}</p>
      <div class="form-actions end">
        <button type="button" class="btn" @click="dialog.close()">Cancel</button>
        <button class="btn btn-primary" :disabled="busy || !password">{{ busy ? 'Checking...' : 'Sign in' }}</button>
      </div>
    </form>
  </dialog>
</template>
