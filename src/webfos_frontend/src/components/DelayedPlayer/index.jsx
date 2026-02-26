/**
 * 검수자용 지연 플레이어 컴포넌트
 * 
 * [advice from AI] 개선 사항:
 * 1. 자동 재생 제거 - 버튼 클릭 시에만 재생
 * 2. 화질 변경 시 재시작 지원
 * 3. 재생 상태 표시
 * 4. 버퍼 상태 상세 표시
 */

import { useEffect, useRef, useState } from 'react'
import { useDelayBuffer } from '../../hooks/useDelayBuffer'
import { DELAY_MS } from '../../utils/constants'
import './styles.css'

export function DelayedPlayer({ videoTrack, audioTrack, quality = 'high', onQualityChange }) {
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
  const [currentQuality, setCurrentQuality] = useState(quality)
  const startedRef = useRef(false)
  
  // 트랙이 준비되면 버퍼링 시작
  useEffect(() => {
    if (videoTrack && audioTrack && !startedRef.current) {
      console.log('[DelayedPlayer] 트랙 준비됨, 버퍼링 시작')
      startedRef.current = true
      setCurrentQuality(quality)
      startBuffer(videoTrack, audioTrack, quality)
    }
    
    return () => {
      if (startedRef.current) {
        startedRef.current = false
        stopBuffer()
      }
    }
  }, [videoTrack, audioTrack])
  
  // 화질 변경 시 재시작
  useEffect(() => {
    if (startedRef.current && quality !== currentQuality) {
      console.log('[DelayedPlayer] 화질 변경:', currentQuality, '->', quality)
      setCurrentQuality(quality)
      setIsPlaying(false)
      stopBuffer()
      
      // 잠시 후 재시작
      setTimeout(() => {
        if (videoTrack && audioTrack) {
          startBuffer(videoTrack, audioTrack, quality)
        }
      }, 100)
    }
  }, [quality, currentQuality, videoTrack, audioTrack, stopBuffer, startBuffer])
  
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
  
  const delaySeconds = (DELAY_MS / 1000).toFixed(1)
  
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
          <span>버퍼링 중... ({delaySeconds}초 지연 준비)</span>
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
          <> | 지연: {bufferStats.bufferHealth.toFixed(1)}s</>
        )}
      </div>
      
      {isReady && !isPlaying && (
        <button className="play-button" onClick={handlePlay}>
          ▶ 재생 시작 ({delaySeconds}초 지연)
        </button>
      )}
      
      {isPlaying && (
        <div className="playing-indicator">
          ● LIVE (−{delaySeconds}초)
        </div>
      )}
    </div>
  )
}

export default DelayedPlayer
