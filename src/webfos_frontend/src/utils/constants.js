/**
 * 전역 상수 정의
 */

// [advice from AI] 지연시간 선택 옵션 (1초부터 선택 가능)
export const DELAY_OPTIONS = [
  { value: 1, label: '1초', toleranceMs: 500 },
  { value: 2, label: '2초', toleranceMs: 500 },
  { value: 3, label: '3초', toleranceMs: 500 },
  { value: 4, label: '4초', toleranceMs: 500 },
  { value: 5, label: '5초', toleranceMs: 500 },
]

// [advice from AI] 기본 지연시간을 DELAY_OPTIONS와 일치시킴
export const DEFAULT_DELAY_SECONDS = 2

export const REALTIME_IDENTITY = 'ingress-hls-source'

export const DELAYED_IDENTITY = 'room-agent-delayed'

// [advice from AI] 고정 비트레이트 설정 (2Mbps) - 해상도 유지 시 텍스트 가독성 충분, 클라이언트 부하 감소
export const FIXED_VIDEO_BITRATE = 2000000  // 2Mbps
export const FIXED_AUDIO_BITRATE = 128000   // 128kbps

export const CONNECTION_STATE = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  RECONNECTING: 'reconnecting',
}
