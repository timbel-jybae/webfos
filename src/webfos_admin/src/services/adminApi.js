const API_BASE = '/api'

export async function fetchRooms() {
  const response = await fetch(`${API_BASE}/admin/rooms`)
  if (!response.ok) {
    throw new Error(`룸 목록 조회 실패: ${response.status}`)
  }
  return response.json()
}

export async function fetchRoomDetail(roomName) {
  const response = await fetch(`${API_BASE}/admin/rooms/${encodeURIComponent(roomName)}`)
  if (!response.ok) {
    throw new Error(`룸 상세 조회 실패: ${response.status}`)
  }
  return response.json()
}
