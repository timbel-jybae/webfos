/**
 * 검수자용 지연 플레이어 컴포넌트
 * 
 * [advice from AI] 개선 사항:
 * 1. 자동 재생 제거 - 버튼 클릭 시에만 재생
 * 2. 지연시간 변경 시 재시작 지원
 * 3. 버퍼 상태 상세 표시
 * 4. 고정 비트레이트 (2Mbps) 사용 - 화질선택 UI 제거
 */

import { useEffect, useRef, useState } from 'react'
import { useDelayBuffer } from '../../hooks/useDelayBuffer'
import { DEFAULT_DELAY_SECONDS } from '../../utils/constants'
import './styles.css'

export function DelayedPlayer({ videoTrack, audioTrack, delay = DEFAULT_DELAY_SECONDS }) {
  const {
    delayedVideoRef,
    isReady,
    isBuffering,
    error,
    bufferStats,
    startBuffer,
    stopBuffer,
    play,
  } = useDelayBuffer()
  
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentDelay, setCurrentDelay] = useState(delay)
  const startedRef = useRef(false)
  
  // 트랙이 준비되면 버퍼링 시작
  useEffect(() => {
    if (videoTrack && audioTrack && !startedRef.current) {
      console.log('[DelayedPlayer] 트랙 준비됨, 버퍼링 시작')
      startedRef.current = true
      setCurrentDelay(delay)
      startBuffer(videoTrack, audioTrack, delay)
    }
    
    return () => {
      if (startedRef.current) {
        startedRef.current = false
        stopBuffer()
      }
    }
  }, [videoTrack, audioTrack])
  
  // 지연시간 변경 시 재시작
  useEffect(() => {
    const delayChanged = delay !== currentDelay
    
    if (startedRef.current && delayChanged) {
      console.log('[DelayedPlayer] 지연시간 변경:', `${currentDelay} -> ${delay}`)
      setCurrentDelay(delay)
      setIsPlaying(false)
      stopBuffer()
      
      // 잠시 후 재시작
      setTimeout(() => {
        if (videoTrack && audioTrack) {
          startBuffer(videoTrack, audioTrack, delay)
        }
      }, 100)
    }
  }, [delay, currentDelay, videoTrack, audioTrack, stopBuffer, startBuffer])
  
  const handlePlay = () => {
    play()
    setIsPlaying(true)
  }
  
  // 비디오 이벤트 핸들러
  useEffect(() => {
    const video = delayedVideoRef.current
    if (!video) return
    
    const onPause = () => setIsPlaying(false)
    const onPlay = () => setIsPlaying(true)
    const onWaiting = () => console.log('[DelayedPlayer] 버퍼링 대기 중...')
    const onPlaying = () => console.log('[DelayedPlayer] 재생 중')
    
    video.addEventListener('pause', onPause)
    video.addEventListener('play', onPlay)
    video.addEventListener('waiting', onWaiting)
    video.addEventListener('playing', onPlaying)
    
    return () => {
      video.removeEventListener('pause', onPause)
      video.removeEventListener('play', onPlay)
      video.removeEventListener('waiting', onWaiting)
      video.removeEventListener('playing', onPlaying)
    }
  }, [delayedVideoRef])
  
  // 현재 지연 설정값 (bufferStats에서 또는 prop에서)
  const displayDelay = bufferStats?.targetDelay ?? delay
  
  return (
    <div className="delayed-player">
      <video
        ref={delayedVideoRef}
        playsInline
        className="video-element"
      />
      
      {isBuffering && (
        <div className="buffering-overlay">
          <div className="spinner" />
          <span>버퍼링 중... ({displayDelay}초 지연 준비)</span>
        </div>
      )}
      
      {error && (
        <div className="error-overlay">
          <span>⚠️ {error}</span>
        </div>
      )}
      
      <div className="buffer-stats">
        처리: {bufferStats?.processed || 0}
        {bufferStats?.bufferHealth !== undefined && (
          <> | 버퍼: {bufferStats.bufferHealth.toFixed(1)}s</>
        )}
        <> | 지연: {displayDelay}s</>
      </div>
      
      {isReady && !isPlaying && (
        <button className="play-button" onClick={handlePlay}>
          ▶ 재생 시작 ({displayDelay}초 지연)
        </button>
      )}
      
      {isPlaying && (
        <div className="playing-indicator">
          ● LIVE (−{displayDelay}초)
        </div>
      )}
    </div>
  )
}

export default DelayedPlayer
