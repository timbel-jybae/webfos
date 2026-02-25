/**
 * 검수자용 지연 버퍼 관리 훅
 * 
 * MediaRecorder + MediaSource를 사용하여 3.5초 지연 재생 구현.
 * - startBuffer(videoTrack, audioTrack, quality): 버퍼링 시작
 * - stopBuffer(): 버퍼링 중지
 * - delayedVideoRef: 지연 비디오 엘리먼트 ref
 * - isReady: 버퍼 준비 완료 여부
 * - play(): 지연 비디오 재생
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { DELAY_MS, QUALITY_OPTIONS } from '../utils/constants'

export function useDelayBuffer() {
  const [isReady, setIsReady] = useState(false)
  const [isBuffering, setIsBuffering] = useState(false)
  const [error, setError] = useState(null)
  
  const delayedVideoRef = useRef(null)
  const delayBufferRef = useRef([])
  const mediaRecorderRef = useRef(null)
  const mediaSourceRef = useRef(null)
  const sourceBufferRef = useRef(null)
  const delayIntervalRef = useRef(null)
  const hiddenVideoRef = useRef(null)
  const isStartedRef = useRef(false)
  
  const cleanup = useCallback(() => {
    console.log('[DelayBuffer] cleanup 시작')
    isStartedRef.current = false
    
    // 인터벌 정리
    if (delayIntervalRef.current) {
      clearInterval(delayIntervalRef.current)
      delayIntervalRef.current = null
    }
    
    // MediaRecorder 정리
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      try {
        mediaRecorderRef.current.stop()
      } catch (e) { /* ignore */ }
    }
    mediaRecorderRef.current = null
    
    // MediaSource 정리
    if (mediaSourceRef.current && mediaSourceRef.current.readyState === 'open') {
      try {
        mediaSourceRef.current.endOfStream()
      } catch (e) { /* ignore */ }
    }
    mediaSourceRef.current = null
    sourceBufferRef.current = null
    
    // Hidden video 정리
    if (hiddenVideoRef.current && hiddenVideoRef.current.parentNode) {
      hiddenVideoRef.current.parentNode.removeChild(hiddenVideoRef.current)
    }
    hiddenVideoRef.current = null
    
    // 버퍼 정리
    delayBufferRef.current = []
    
    setIsReady(false)
    setIsBuffering(false)
  }, [])

  // processDelayBuffer를 ref로 저장 (순환 의존성 방지)
  const processDelayBufferRef = useRef(null)
  
  processDelayBufferRef.current = () => {
    if (!sourceBufferRef.current || sourceBufferRef.current.updating) return
    if (mediaSourceRef.current?.readyState !== 'open') return
    
    const now = Date.now()
    while (delayBufferRef.current.length > 0) {
      const oldest = delayBufferRef.current[0]
      if (now - oldest.timestamp >= DELAY_MS) {
        delayBufferRef.current.shift()
        oldest.blob.arrayBuffer().then((buffer) => {
          try {
            if (sourceBufferRef.current && 
                !sourceBufferRef.current.updating && 
                mediaSourceRef.current?.readyState === 'open') {
              sourceBufferRef.current.appendBuffer(buffer)
            }
          } catch (err) {
            console.warn('[DelayBuffer] appendBuffer error:', err)
          }
        })
        break
      } else {
        break
      }
    }
  }
  
  const startBuffer = useCallback((videoTrack, audioTrack, quality = 'high') => {
    if (!videoTrack || !audioTrack) {
      console.warn('[DelayBuffer] 비디오 또는 오디오 트랙 없음')
      return
    }
    
    // 이미 시작된 경우 스킵
    if (isStartedRef.current || mediaRecorderRef.current) {
      console.log('[DelayBuffer] 이미 시작됨, 스킵')
      return
    }
    
    isStartedRef.current = true
    setIsBuffering(true)
    setError(null)
    
    const videoMST = videoTrack.mediaStreamTrack
    const audioMST = audioTrack.mediaStreamTrack
    
    console.log('[DelayBuffer] 지연 버퍼 시작', { 
      video: { readyState: videoMST.readyState, muted: videoMST.muted },
      audio: { readyState: audioMST.readyState, muted: audioMST.muted }
    })
    
    // Hidden video 생성 (captureStream 사용)
    const hiddenVideo = document.createElement('video')
    hiddenVideo.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:1px;height:1px;'
    hiddenVideo.autoplay = true
    hiddenVideo.playsInline = true
    hiddenVideo.muted = true
    document.body.appendChild(hiddenVideo)
    hiddenVideoRef.current = hiddenVideo
    
    // 원본 트랙을 hidden video에 연결
    const originalStream = new MediaStream()
    originalStream.addTrack(videoMST)
    originalStream.addTrack(audioMST)
    hiddenVideo.srcObject = originalStream
    
    const startCaptureAndRecord = () => {
      console.log('[DelayBuffer] hidden video loaded, starting capture')
      hiddenVideo.play().catch(e => console.warn('[DelayBuffer] play error:', e))
      
      // captureStream으로 녹화용 스트림 생성
      setTimeout(() => {
        if (!isStartedRef.current) return
        
        try {
          const capturedStream = hiddenVideo.captureStream 
            ? hiddenVideo.captureStream() 
            : hiddenVideo.mozCaptureStream?.()
          
          if (!capturedStream) {
            throw new Error('captureStream not supported')
          }
          
          console.log('[DelayBuffer] capturedStream tracks:', 
            capturedStream.getTracks().map(t => `${t.kind}:${t.readyState}`))
          
          // MediaRecorder 시작
          const mimeTypes = [
            'video/webm;codecs=vp9,opus',
            'video/webm;codecs=vp8,opus',
            'video/webm',
          ]
          const mimeType = mimeTypes.find(mt => MediaRecorder.isTypeSupported(mt)) || ''
          const qualityConfig = QUALITY_OPTIONS[quality] || QUALITY_OPTIONS.high
          
          console.log('[DelayBuffer] mimeType:', mimeType, '화질:', qualityConfig.label)
          
          const recorder = new MediaRecorder(capturedStream, {
            mimeType,
            videoBitsPerSecond: qualityConfig.videoBitsPerSecond,
            audioBitsPerSecond: qualityConfig.audioBitsPerSecond,
          })
          mediaRecorderRef.current = recorder
          
          recorder.ondataavailable = (e) => {
            if (e.data.size > 0) {
              delayBufferRef.current.push({ timestamp: Date.now(), blob: e.data })
              console.log('[DelayBuffer] chunk:', e.data.size, 'bytes, buffer:', delayBufferRef.current.length)
            }
          }
          
          recorder.onerror = (e) => {
            console.error('[DelayBuffer] recorder error:', e)
            setError('녹화 오류')
          }
          
          recorder.onstart = () => console.log('[DelayBuffer] recorder started')
          recorder.onstop = () => {
            console.log('[DelayBuffer] recorder stopped')
            if (hiddenVideo.parentNode) {
              hiddenVideo.parentNode.removeChild(hiddenVideo)
            }
          }
          
          recorder.start(500) // 500ms 간격
          
          // MediaSource 설정
          const mediaSource = new MediaSource()
          mediaSourceRef.current = mediaSource
          
          if (delayedVideoRef.current) {
            delayedVideoRef.current.src = URL.createObjectURL(mediaSource)
          }
          
          mediaSource.addEventListener('sourceopen', () => {
            console.log('[DelayBuffer] MediaSource sourceopen')
            
            try {
              const sourceBuffer = mediaSource.addSourceBuffer(mimeType || 'video/webm')
              sourceBufferRef.current = sourceBuffer
              
              sourceBuffer.addEventListener('error', (e) => {
                console.error('[DelayBuffer] sourceBuffer error:', e)
              })
              
              sourceBuffer.addEventListener('updateend', () => {
                processDelayBufferRef.current?.()
              })
              
              // 지연 버퍼 처리 인터벌
              delayIntervalRef.current = setInterval(() => {
                processDelayBufferRef.current?.()
              }, 200)
              
              setIsReady(true)
              setIsBuffering(false)
              console.log('[DelayBuffer] 준비 완료')
              
            } catch (err) {
              console.error('[DelayBuffer] sourceBuffer 생성 실패:', err)
              setError('sourceBuffer 생성 실패: ' + err.message)
              setIsBuffering(false)
            }
          })
          
        } catch (err) {
          console.error('[DelayBuffer] captureStream 실패:', err)
          setError('captureStream 실패: ' + err.message)
          setIsBuffering(false)
          isStartedRef.current = false
        }
      }, 500)
    }
    
    hiddenVideo.onloadedmetadata = startCaptureAndRecord
    
    hiddenVideo.onerror = (e) => {
      console.error('[DelayBuffer] hidden video error:', e)
      setError('비디오 로드 실패')
      setIsBuffering(false)
      isStartedRef.current = false
    }
  }, []) // cleanup 의존성 제거
  
  const play = useCallback(() => {
    if (delayedVideoRef.current) {
      delayedVideoRef.current.play()
        .catch(e => console.warn('[DelayBuffer] play error:', e))
    }
  }, [])
  
  const stopBuffer = useCallback(() => {
    cleanup()
  }, [cleanup])
  
  // 컴포넌트 언마운트 시 정리
  useEffect(() => {
    return () => {
      cleanup()
    }
  }, [cleanup])
  
  return {
    delayedVideoRef,
    isReady,
    isBuffering,
    error,
    startBuffer,
    stopBuffer,
    play,
  }
}

export default useDelayBuffer
