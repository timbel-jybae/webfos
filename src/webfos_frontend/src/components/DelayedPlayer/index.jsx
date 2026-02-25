/**
 * 검수자용 지연 플레이어 컴포넌트
 * 
 * 클라이언트 측 버퍼링을 통한 3.5초 지연 재생.
 */

import { useEffect, useRef } from 'react'
import { useDelayBuffer } from '../../hooks/useDelayBuffer'
import './styles.css'

export function DelayedPlayer({ videoTrack, audioTrack, quality = 'high' }) {
  const {
    delayedVideoRef,
    isReady,
    isBuffering,
    error,
    startBuffer,
    stopBuffer,
    play,
  } = useDelayBuffer()
  
  const startedRef = useRef(false)
  
  // 트랙이 준비되면 버퍼링 시작
  useEffect(() => {
    if (videoTrack && audioTrack && !startedRef.current) {
      console.log('[DelayedPlayer] 트랙 준비됨, 버퍼링 시작')
      startedRef.current = true
      startBuffer(videoTrack, audioTrack, quality)
    }
    
    return () => {
      if (startedRef.current) {
        startedRef.current = false
        stopBuffer()
      }
    }
  }, [videoTrack, audioTrack]) // quality, startBuffer 제거 - 초기 1회만 실행
  
  return (
    <div className="delayed-player">
      <video
        ref={delayedVideoRef}
        autoPlay
        playsInline
        className="video-element"
      />
      
      {isBuffering && (
        <div className="buffering-overlay">
          <div className="spinner" />
          <span>버퍼링 중...</span>
        </div>
      )}
      
      {error && (
        <div className="error-overlay">
          <span>⚠️ {error}</span>
        </div>
      )}
      
      {isReady && (
        <button className="play-button" onClick={play}>
          ▶ 재생
        </button>
      )}
    </div>
  )
}

export default DelayedPlayer
