/**
 * 실시간 비디오 플레이어 컴포넌트
 * 
 * LiveKit 비디오/오디오 트랙을 직접 재생.
 */

import { useRef, useEffect } from 'react'
import './styles.css'

export function VideoPlayer({ videoTrack, audioTrack, onAudioReady }) {
  const videoContainerRef = useRef(null)
  const audioContainerRef = useRef(null)
  const videoElementRef = useRef(null)
  const audioElementRef = useRef(null)
  
  // 비디오 트랙 연결
  useEffect(() => {
    if (!videoTrack) return
    
    const container = videoContainerRef.current
    if (!container) return
    
    // 기존 엘리먼트 제거
    if (videoElementRef.current) {
      videoTrack.detach(videoElementRef.current)
      videoElementRef.current.remove()
      videoElementRef.current = null
    }
    
    // attach()는 새 엘리먼트를 반환
    const element = videoTrack.attach()
    element.style.width = '100%'
    element.style.height = '100%'
    element.style.objectFit = 'contain'
    element.autoplay = true
    element.playsInline = true
    container.appendChild(element)
    videoElementRef.current = element
    
    console.log('[VideoPlayer] 비디오 트랙 연결')
    
    return () => {
      if (videoElementRef.current) {
        videoTrack.detach(videoElementRef.current)
        videoElementRef.current.remove()
        videoElementRef.current = null
      }
    }
  }, [videoTrack])
  
  // 오디오 트랙 연결
  useEffect(() => {
    if (!audioTrack) return
    
    // 기존 엘리먼트 제거
    if (audioElementRef.current) {
      audioTrack.detach(audioElementRef.current)
      audioElementRef.current.remove()
      audioElementRef.current = null
    }
    
    // attach()는 새 엘리먼트를 반환
    const element = audioTrack.attach()
    element.autoplay = true
    element.volume = 1.0
    document.body.appendChild(element)
    audioElementRef.current = element
    
    console.log('[VideoPlayer] 오디오 트랙 연결')
    onAudioReady?.()
    
    return () => {
      if (audioElementRef.current) {
        audioTrack.detach(audioElementRef.current)
        audioElementRef.current.remove()
        audioElementRef.current = null
      }
    }
  }, [audioTrack, onAudioReady])
  
  return (
    <div className="video-player">
      <div ref={videoContainerRef} className="video-container" />
      <div ref={audioContainerRef} className="audio-container" style={{ display: 'none' }} />
    </div>
  )
}

export default VideoPlayer
