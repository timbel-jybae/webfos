/**
 * 검수자용 지연 버퍼 관리 훅 (싱글톤 버전)
 * 
 * [advice from AI] React Strict Mode 중복 실행 방지를 위해 모듈 레벨 싱글톤 사용
 * 
 * MediaRecorder + MediaSource를 사용하여 지연 재생 구현.
 * - startBuffer(videoTrack, audioTrack, quality): 버퍼링 시작
 * - stopBuffer(): 버퍼링 중지
 * - delayedVideoRef: 지연 비디오 엘리먼트 ref
 * - isReady: 버퍼 준비 완료 여부
 * - play(): 지연 비디오 재생
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { DELAY_MS, QUALITY_OPTIONS } from '../utils/constants'

const MAX_BUFFER_CHUNKS = 30
const PROCESS_INTERVAL_MS = 50
const MAX_RETRY_COUNT = 3
const TARGET_DELAY_SECONDS = DELAY_MS / 1000
const MIN_BUFFER_SECONDS = 0.5
const BUFFER_TOLERANCE = 0.5

// [advice from AI] 모듈 레벨 싱글톤 상태
const globalState = {
  isStarted: false,
  isReady: false,
  chunkQueue: [],
  mediaRecorder: null,
  mediaSource: null,
  sourceBuffer: null,
  processInterval: null,
  bufferMonitorInterval: null,
  hiddenVideo: null,
  isProcessing: false,
  processedCount: 0,
  videoElement: null,
  stateCallbacks: new Set(),
  captureTimeoutId: null,
  startId: 0,
  lastBufferHealth: 0,
}

function notifyStateChange(state) {
  globalState.stateCallbacks.forEach(cb => cb(state))
}

function cleanupGlobal() {
  console.log('[DelayBuffer] cleanup 시작')
  globalState.isStarted = false
  globalState.isReady = false
  globalState.isProcessing = false
  globalState.startId++
  
  if (globalState.captureTimeoutId) {
    clearTimeout(globalState.captureTimeoutId)
    globalState.captureTimeoutId = null
  }
  
  if (globalState.processInterval) {
    clearInterval(globalState.processInterval)
    globalState.processInterval = null
  }
  
  if (globalState.bufferMonitorInterval) {
    clearInterval(globalState.bufferMonitorInterval)
    globalState.bufferMonitorInterval = null
  }
  
  if (globalState.mediaRecorder && globalState.mediaRecorder.state !== 'inactive') {
    try {
      globalState.mediaRecorder.stop()
    } catch (e) { /* ignore */ }
  }
  globalState.mediaRecorder = null
  
  if (globalState.mediaSource && globalState.mediaSource.readyState === 'open') {
    try {
      globalState.mediaSource.endOfStream()
    } catch (e) { /* ignore */ }
  }
  globalState.mediaSource = null
  globalState.sourceBuffer = null
  
  if (globalState.hiddenVideo && globalState.hiddenVideo.parentNode) {
    globalState.hiddenVideo.parentNode.removeChild(globalState.hiddenVideo)
  }
  globalState.hiddenVideo = null
  
  globalState.chunkQueue = []
  globalState.processedCount = 0
  globalState.lastBufferHealth = 0
  
  // 비디오 playbackRate 복원
  if (globalState.videoElement) {
    globalState.videoElement.playbackRate = 1.0
  }
  
  notifyStateChange({ isReady: false, isBuffering: false, error: null, bufferStats: { chunks: 0, processed: 0, bufferHealth: 0 } })
}

function waitForSourceBuffer() {
  return new Promise((resolve) => {
    const sb = globalState.sourceBuffer
    if (!sb || !sb.updating) {
      resolve()
      return
    }
    
    const onUpdateEnd = () => {
      sb.removeEventListener('updateend', onUpdateEnd)
      resolve()
    }
    sb.addEventListener('updateend', onUpdateEnd)
  })
}

async function appendBufferSafe(arrayBuffer, retryCount = 0) {
  const sb = globalState.sourceBuffer
  const ms = globalState.mediaSource
  
  if (!sb || !ms || ms.readyState !== 'open') {
    return false
  }
  
  try {
    await waitForSourceBuffer()
    
    if (!sb || !ms || ms.readyState !== 'open') {
      return false
    }
    
    sb.appendBuffer(arrayBuffer)
    await waitForSourceBuffer()
    return true
    
  } catch (err) {
    console.warn(`[DelayBuffer] appendBuffer 오류 (시도 ${retryCount + 1}):`, err.message)
    
    if (err.name === 'QuotaExceededError' && sb && !sb.updating) {
      try {
        const buffered = sb.buffered
        if (buffered.length > 0) {
          const removeEnd = buffered.start(0) + 5
          sb.remove(buffered.start(0), removeEnd)
          await waitForSourceBuffer()
          console.log('[DelayBuffer] 오래된 버퍼 제거 완료')
        }
      } catch (removeErr) {
        console.warn('[DelayBuffer] 버퍼 제거 실패:', removeErr)
      }
    }
    
    if (retryCount < MAX_RETRY_COUNT) {
      await new Promise(r => setTimeout(r, 100 * (retryCount + 1)))
      return appendBufferSafe(arrayBuffer, retryCount + 1)
    }
    
    return false
  }
}

function getBufferHealth() {
  const video = globalState.videoElement
  const sb = globalState.sourceBuffer
  
  if (!video || !sb) return 0
  
  try {
    const buffered = sb.buffered
    if (buffered.length === 0) return 0
    
    const currentTime = video.currentTime
    for (let i = 0; i < buffered.length; i++) {
      if (currentTime >= buffered.start(i) && currentTime <= buffered.end(i)) {
        return buffered.end(i) - currentTime
      }
    }
    return 0
  } catch (e) {
    return 0
  }
}

function monitorBuffer() {
  const video = globalState.videoElement
  const sb = globalState.sourceBuffer
  if (!video || !sb) return
  
  const bufferHealth = getBufferHealth()
  globalState.lastBufferHealth = bufferHealth
  
  const minRequiredBuffer = TARGET_DELAY_SECONDS - BUFFER_TOLERANCE
  const maxAllowedBuffer = TARGET_DELAY_SECONDS + BUFFER_TOLERANCE
  
  // [advice from AI] 버퍼 범위 유지: TARGET ± TOLERANCE
  
  if (!video.paused) {
    // 재생 중일 때
    
    if (bufferHealth < minRequiredBuffer) {
      // 버퍼 부족 - 일시정지하고 버퍼 쌓기
      console.log('[DelayBuffer] 버퍼 부족, 일시정지:', bufferHealth.toFixed(1), '초')
      video.pause()
      notifyStateChange({ isBuffering: true })
    } else if (bufferHealth > maxAllowedBuffer && sb.buffered.length > 0) {
      // 버퍼 초과 - seek로 따라잡기
      const bufferEnd = sb.buffered.end(sb.buffered.length - 1)
      const targetTime = bufferEnd - TARGET_DELAY_SECONDS
      
      if (targetTime > video.currentTime + BUFFER_TOLERANCE) {
        console.log('[DelayBuffer] 버퍼 초과, seek:', 
          video.currentTime.toFixed(1), '->', targetTime.toFixed(1))
        video.currentTime = targetTime
      }
    }
  } else {
    // 일시정지 상태일 때
    
    if (bufferHealth >= TARGET_DELAY_SECONDS && sb.buffered.length > 0) {
      // 버퍼가 충분히 쌓이면 올바른 위치에서 재생 재개
      const bufferEnd = sb.buffered.end(sb.buffered.length - 1)
      const targetTime = bufferEnd - TARGET_DELAY_SECONDS
      
      console.log('[DelayBuffer] 버퍼 충분, 재생 재개:', targetTime.toFixed(1))
      video.currentTime = targetTime
      video.play().catch(e => console.warn('[DelayBuffer] play error:', e))
      notifyStateChange({ isBuffering: false })
    }
  }
  
  // playbackRate는 항상 1.0
  if (video.playbackRate !== 1.0) {
    video.playbackRate = 1.0
  }
  
  notifyStateChange({
    bufferStats: {
      chunks: globalState.chunkQueue.length,
      processed: globalState.processedCount,
      bufferHealth,
    }
  })
}

async function processQueue() {
  if (globalState.isProcessing) return
  if (!globalState.sourceBuffer || !globalState.mediaSource) return
  if (globalState.mediaSource.readyState !== 'open') return
  
  globalState.isProcessing = true
  
  try {
    // [advice from AI] 단순화: 청크를 즉시 SourceBuffer에 추가
    // 지연은 버퍼 + seek로 관리
    
    // 큐가 너무 많으면 오래된 것 제거
    while (globalState.chunkQueue.length > MAX_BUFFER_CHUNKS) {
      globalState.chunkQueue.shift()
    }
    
    // 모든 대기 중인 청크를 즉시 처리
    while (globalState.chunkQueue.length > 0) {
      const chunk = globalState.chunkQueue.shift()
      
      try {
        const arrayBuffer = await chunk.blob.arrayBuffer()
        const success = await appendBufferSafe(arrayBuffer)
        
        if (success) {
          globalState.processedCount++
        }
      } catch (err) {
        console.warn('[DelayBuffer] 청크 처리 실패, 스킵:', err)
      }
    }
    
    const bufferHealth = getBufferHealth()
    notifyStateChange({
      bufferStats: {
        chunks: globalState.chunkQueue.length,
        processed: globalState.processedCount,
        bufferHealth,
      }
    })
    
  } finally {
    globalState.isProcessing = false
  }
}

function startBufferGlobal(videoTrack, audioTrack, quality, videoElement) {
  if (!videoTrack || !audioTrack) {
    console.warn('[DelayBuffer] 비디오 또는 오디오 트랙 없음')
    return
  }
  
  // 이미 시작된 경우 스킵
  if (globalState.isStarted) {
    console.log('[DelayBuffer] 이미 시작됨, 스킵')
    return
  }
  
  globalState.isStarted = true
  globalState.startId++
  const currentStartId = globalState.startId
  globalState.videoElement = videoElement
  notifyStateChange({ isBuffering: true, error: null })
  
  const videoMST = videoTrack.mediaStreamTrack
  const audioMST = audioTrack.mediaStreamTrack
  
  console.log('[DelayBuffer] 지연 버퍼 시작', { 
    video: { readyState: videoMST.readyState, muted: videoMST.muted },
    audio: { readyState: audioMST.readyState, muted: audioMST.muted },
    delayMs: DELAY_MS,
    startId: currentStartId,
  })
  
  const hiddenVideo = document.createElement('video')
  hiddenVideo.style.cssText = 'position:fixed;top:-9999px;left:-9999px;width:1px;height:1px;'
  hiddenVideo.autoplay = true
  hiddenVideo.playsInline = true
  hiddenVideo.muted = true
  document.body.appendChild(hiddenVideo)
  globalState.hiddenVideo = hiddenVideo
  
  const originalStream = new MediaStream()
  originalStream.addTrack(videoMST)
  originalStream.addTrack(audioMST)
  hiddenVideo.srcObject = originalStream
  
  const startCaptureAndRecord = () => {
    console.log('[DelayBuffer] hidden video loaded, starting capture, startId:', currentStartId)
    hiddenVideo.play().catch(e => console.warn('[DelayBuffer] play error:', e))
    
    globalState.captureTimeoutId = setTimeout(() => {
      // startId가 변경되었으면 이 콜백은 무효
      if (globalState.startId !== currentStartId) {
        console.log('[DelayBuffer] setTimeout 무효화됨 (startId 불일치)')
        return
      }
      if (!globalState.isStarted) return
      
      try {
        const capturedStream = hiddenVideo.captureStream 
          ? hiddenVideo.captureStream() 
          : hiddenVideo.mozCaptureStream?.()
        
        if (!capturedStream) {
          throw new Error('captureStream not supported')
        }
        
        const tracks = capturedStream.getTracks()
        console.log('[DelayBuffer] capturedStream tracks:', 
          tracks.map(t => `${t.kind}:${t.readyState}`))
        
        if (tracks.length === 0) {
          throw new Error('capturedStream에 트랙이 없음')
        }
        
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
        globalState.mediaRecorder = recorder
        
        recorder.ondataavailable = (e) => {
          // startId가 변경되었으면 이 데이터는 무시
          if (globalState.startId !== currentStartId) return
          if (e.data.size > 0 && globalState.isStarted) {
            globalState.chunkQueue.push({ 
              timestamp: Date.now(), 
              blob: e.data,
            })
            // 로그는 10개마다 출력 (성능 최적화)
            if (globalState.chunkQueue.length % 10 === 0) {
              console.log('[DelayBuffer] 청크 큐:', globalState.chunkQueue.length)
            }
          }
        }
        
        recorder.onerror = (e) => {
          console.error('[DelayBuffer] recorder error:', e)
          notifyStateChange({ error: '녹화 오류: ' + (e.error?.message || 'unknown') })
        }
        
        recorder.onstart = () => {
          console.log('[DelayBuffer] recorder started')
        }
        
        recorder.onstop = () => {
          console.log('[DelayBuffer] recorder stopped')
          if (hiddenVideo.parentNode) {
            hiddenVideo.parentNode.removeChild(hiddenVideo)
          }
        }
        
        recorder.start(500)
        
        const mediaSource = new MediaSource()
        globalState.mediaSource = mediaSource
        
        if (globalState.videoElement) {
          globalState.videoElement.src = URL.createObjectURL(mediaSource)
        }
        
        mediaSource.addEventListener('sourceopen', () => {
          console.log('[DelayBuffer] MediaSource sourceopen')
          
          try {
            const sourceBuffer = mediaSource.addSourceBuffer(mimeType || 'video/webm')
            globalState.sourceBuffer = sourceBuffer
            
            sourceBuffer.mode = 'sequence'
            
            sourceBuffer.addEventListener('error', (e) => {
              console.error('[DelayBuffer] sourceBuffer error:', e)
            })
            
            globalState.processInterval = setInterval(() => {
              processQueue()
            }, PROCESS_INTERVAL_MS)
            
            globalState.bufferMonitorInterval = setInterval(() => {
              monitorBuffer()
              
              // [advice from AI] 버퍼가 충분히 쌓이면 isReady = true
              const bufferHealth = getBufferHealth()
              if (bufferHealth >= TARGET_DELAY_SECONDS && !globalState.isReady) {
                globalState.isReady = true
                notifyStateChange({ isReady: true, isBuffering: false })
                console.log('[DelayBuffer] 준비 완료, 버퍼:', bufferHealth.toFixed(1), '초')
              }
            }, 500)
            
            console.log('[DelayBuffer] 버퍼링 시작, 목표 지연:', TARGET_DELAY_SECONDS, '초')
            
          } catch (err) {
            console.error('[DelayBuffer] sourceBuffer 생성 실패:', err)
            notifyStateChange({ error: 'sourceBuffer 생성 실패: ' + err.message, isBuffering: false })
          }
        })
        
        mediaSource.addEventListener('sourceended', () => {
          console.log('[DelayBuffer] MediaSource sourceended')
        })
        
        mediaSource.addEventListener('sourceclose', () => {
          console.log('[DelayBuffer] MediaSource sourceclose')
        })
        
      } catch (err) {
        console.error('[DelayBuffer] captureStream 실패:', err)
        notifyStateChange({ error: 'captureStream 실패: ' + err.message, isBuffering: false })
        globalState.isStarted = false
      }
    }, 500)
  }
  
  hiddenVideo.onloadedmetadata = () => {
    // startId가 변경되었으면 이 콜백은 무효
    if (globalState.startId !== currentStartId) {
      console.log('[DelayBuffer] onloadedmetadata 무효화됨 (startId 불일치)')
      return
    }
    startCaptureAndRecord()
  }
  
  hiddenVideo.onerror = (e) => {
    if (globalState.startId !== currentStartId) return
    console.error('[DelayBuffer] hidden video error:', e)
    notifyStateChange({ error: '비디오 로드 실패', isBuffering: false })
    globalState.isStarted = false
  }
}

export function useDelayBuffer() {
  const [isReady, setIsReady] = useState(false)
  const [isBuffering, setIsBuffering] = useState(false)
  const [error, setError] = useState(null)
  const [bufferStats, setBufferStats] = useState({ chunks: 0, processed: 0 })
  
  const delayedVideoRef = useRef(null)
  
  // 상태 변경 콜백 등록
  useEffect(() => {
    const callback = (state) => {
      if (state.isReady !== undefined) setIsReady(state.isReady)
      if (state.isBuffering !== undefined) setIsBuffering(state.isBuffering)
      if (state.error !== undefined) setError(state.error)
      if (state.bufferStats !== undefined) setBufferStats(state.bufferStats)
    }
    
    globalState.stateCallbacks.add(callback)
    
    return () => {
      globalState.stateCallbacks.delete(callback)
    }
  }, [])
  
  const startBuffer = useCallback((videoTrack, audioTrack, quality = 'high') => {
    startBufferGlobal(videoTrack, audioTrack, quality, delayedVideoRef.current)
  }, [])
  
  const play = useCallback(() => {
    const video = delayedVideoRef.current
    const sb = globalState.sourceBuffer
    
    if (video && sb && sb.buffered.length > 0) {
      // [advice from AI] 재생 시작 시 올바른 지연 위치로 이동
      const bufferEnd = sb.buffered.end(sb.buffered.length - 1)
      const targetTime = Math.max(0, bufferEnd - TARGET_DELAY_SECONDS)
      
      console.log('[DelayBuffer] 재생 시작, 위치:', targetTime.toFixed(1), 
        '(버퍼 끝:', bufferEnd.toFixed(1), ')')
      
      video.currentTime = targetTime
      video.play()
        .catch(e => console.warn('[DelayBuffer] play error:', e))
    } else if (video) {
      video.play()
        .catch(e => console.warn('[DelayBuffer] play error:', e))
    }
  }, [])
  
  const stopBuffer = useCallback(() => {
    cleanupGlobal()
  }, [])
  
  // 컴포넌트 언마운트 시 정리 (단, 첫 언마운트만)
  useEffect(() => {
    return () => {
      // React Strict Mode에서 두 번째 마운트를 위해 cleanup하지 않음
      // 실제 언마운트 시에만 cleanup (globalState.stateCallbacks가 비면)
      setTimeout(() => {
        if (globalState.stateCallbacks.size === 0) {
          cleanupGlobal()
        }
      }, 100)
    }
  }, [])
  
  return {
    delayedVideoRef,
    isReady,
    isBuffering,
    error,
    bufferStats,
    startBuffer,
    stopBuffer,
    play,
  }
}

export default useDelayBuffer
