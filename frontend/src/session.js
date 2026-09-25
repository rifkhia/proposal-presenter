import { reactive } from 'vue'
import { api } from './api'

// Editor sign-in state. `enabled` is false when the server has no EDIT_PASSWORD_HASH.
export const session = reactive({
  enabled: false,
  signedIn: false,

  async refresh() {
    try {
      Object.assign(this, toState(await api.authStatus()))
    } catch {
      // leave editing hidden if the status can't be read
    }
  },

  async signIn(password) {
    Object.assign(this, toState(await api.signIn(password)))
  },

  async signOut() {
    Object.assign(this, toState(await api.signOut()))
  },
})

const toState = (s) => ({ enabled: s.enabled, signedIn: s.signed_in })
