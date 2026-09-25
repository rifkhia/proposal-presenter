async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let message = `${res.status} ${res.statusText}`
    try {
      const data = await res.json()
      if (typeof data.detail === 'string') message = data.detail
      else if (Array.isArray(data.detail)) message = data.detail.map((d) => d.msg).join(', ')
    } catch {
      // non-JSON error body; keep the status text
    }
    const error = new Error(message)
    error.status = res.status
    throw error
  }
  return res.status === 204 ? null : res.json()
}

// Proposal paths may contain folders ("team/q3.md"); encode each segment but keep the slashes.
const encodePath = (path) => path.split('/').map(encodeURIComponent).join('/')

export const api = {
  listProposals: () => request('/api/proposals'),
  getProposal: (path) => request(`/api/proposals/${encodePath(path)}`),
  saveProposal: (path, content, baseVersion, force = false) =>
    request(`/api/proposals/${encodePath(path)}`, {
      method: 'PUT',
      body: JSON.stringify({ content, base_version: baseVersion, force }),
    }),
  authStatus: () => request('/api/auth'),
  signIn: (password) => request('/api/auth/login', { method: 'POST', body: JSON.stringify({ password }) }),
  signOut: () => request('/api/auth/logout', { method: 'POST' }),
  listComments: (path) => request(`/api/comments?proposal=${encodeURIComponent(path)}`),
  addComment: (comment) => request('/api/comments', { method: 'POST', body: JSON.stringify(comment) }),
  resolveComment: (id, resolved, by) =>
    request(`/api/comments/${id}`, { method: 'PATCH', body: JSON.stringify({ resolved, by }) }),
  deleteComment: (id) => request(`/api/comments/${id}`, { method: 'DELETE' }),
}

export { encodePath }
