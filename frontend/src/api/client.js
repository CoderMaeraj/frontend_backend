// Single place that decides: dummy data or real backend.
// Implemented APIs always call the backend (http). request() only serves the pages whose
// backend APIs do not exist yet; set VITE_USE_MOCK=false to send those to the backend too.
export const USE_MOCK = import.meta.env.VITE_USE_MOCK !== 'false'
const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:5000/api'

export const storage = {
  get(key) { try { return localStorage.getItem(key) } catch { return null } },
  set(key, value) { try { localStorage.setItem(key, value) } catch { /* ignore */ } },
  remove(key) { try { localStorage.removeItem(key) } catch { /* ignore */ } }
}

export async function http({ url, method = 'GET', params, data }) {
  const query = params
    ? '?' + new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null)).toString()
    : ''
  const token = storage.get('mc_token')
  let res
  try {
    res = await fetch(BASE_URL + url + query, {
      method,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      body: data ? JSON.stringify(data) : undefined
    })
  } catch {
    throw new Error('Cannot reach the server. Please make sure the backend is running.')
  }
  const body = await res.json().catch(() => ({}))
  if (!res.ok) {
    const err = new Error(body.message || `Request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return body
}

const clone = (v) => (v === undefined ? v : JSON.parse(JSON.stringify(v)))
const wait = () => new Promise((r) => setTimeout(r, 250 + Math.random() * 250))

/**
 * request({ url, method, params, data }, mockFn)
 * - mock mode: runs mockFn() after a short delay (to show loaders)
 * - real mode: calls the backend with the same url/method/body
 */
export async function request(config, mockFn) {
  if (!USE_MOCK) return http(config)
  await wait()
  return clone(mockFn())
}
