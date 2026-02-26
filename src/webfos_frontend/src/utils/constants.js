/**
 * 전역 상수 정의
 */

export const DELAY_MS = parseInt(import.meta.env.VITE_DEFAULT_DELAY_MS || '3500', 10)

export const REALTIME_IDENTITY = 'ingress-hls-source'

export const DELAYED_IDENTITY = 'room-agent-delayed'

export const QUALITY_OPTIONS = {
  low: { label: '저화질 (1Mbps)', videoBitsPerSecond: 1000000, audioBitsPerSecond: 64000 },
  medium: { label: '중화질 (3Mbps)', videoBitsPerSecond: 3000000, audioBitsPerSecond: 128000 },
  high: { label: '고화질 (5Mbps)', videoBitsPerSecond: 5000000, audioBitsPerSecond: 128000 },
  ultra: { label: '최고화질 (8Mbps)', videoBitsPerSecond: 8000000, audioBitsPerSecond: 192000 },
}

export const CONNECTION_STATE = {
  DISCONNECTED: 'disconnected',
  CONNECTING: 'connecting',
  CONNECTED: 'connected',
  RECONNECTING: 'reconnecting',
}
