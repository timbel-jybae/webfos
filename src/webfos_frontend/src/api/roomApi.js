/**
 * 백엔드 API 호출 모듈
 */

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

/**
 * 채널 목록 조회
 * @returns {Promise<{channels: Array<{id, name, hls_url, description, is_active}>}>}
 */
export async function listChannels() {
  const res = await fetch(`${API_BASE}/api/channels`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '채널 목록 조회 실패')
  }
  return res.json()
}

/**
 * [advice from AI] 채널 입장 — role 기반 동적 참가.
 * UUID identity + 토큰 1개를 반환받는다.
 *
 * @param {string} channelId - 채널 ID
 * @param {string} role - "participant" 또는 "reviewer"
 * @returns {Promise<{channel_id, channel_name, ws_url, room, identity, name, role, token}>}
 */
export async function joinChannel(channelId, role = 'participant') {
  const res = await fetch(`${API_BASE}/api/channels/${channelId}/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '채널 입장 실패')
  }
  return res.json()
}

/**
 * 헬스체크
 * @returns {Promise<{status: string}>}
 */
export async function healthCheck() {
  const res = await fetch(`${API_BASE}/api/health`)
  return res.json()
}
