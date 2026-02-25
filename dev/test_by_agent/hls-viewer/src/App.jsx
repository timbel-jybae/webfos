import { useState, useRef, useEffect, useCallback } from 'react'
import { Room, RoomEvent, Track } from 'livekit-client'
import './App.css'

const API_BASE = '' // Vite proxy: /api -> localhost:8000

const REALTIME_IDENTITY = 'ingress-hls-source'
// [advice from AI] 클라이언트 측 지연 버퍼 방식: 서버 측 지연 Ingress 불필요
const DELAY_MS = 3500 // 3.5초 지연

// [advice from AI] 화질 옵션 설정 (비트레이트)
const QUALITY_OPTIONS = {
  low: { label: '저화질 (1Mbps)', videoBitsPerSecond: 1000000, audioBitsPerSecond: 64000 },
  medium: { label: '중화질 (3Mbps)', videoBitsPerSecond: 3000000, audioBitsPerSecond: 128000 },
  high: { label: '고화질 (5Mbps)', videoBitsPerSecond: 5000000, audioBitsPerSecond: 128000 },
  ultra: { label: '최고화질 (8Mbps)', videoBitsPerSecond: 8000000, audioBitsPerSecond: 192000 },
}

function App() {
  const [status, setStatus] = useState('테스트 시작 버튼을 눌러주세요.')
  const [isConnected, setIsConnected] = useState(false)
  const [tracksInfo, setTracksInfo] = useState('')
  const [hasAudioTracks, setHasAudioTracks] = useState(false)
  const [showAudioUnlock, setShowAudioUnlock] = useState(false)
  const [prepareData, setPrepareData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const videoContainerRef = useRef(null)
  const roomRef = useRef(null)
  const audioElementsRef = useRef([])

  // [advice from AI] 검수자용 클라이언트 측 지연 버퍼
  const delayBufferRef = useRef([]) // { timestamp, blob }[]
  const mediaRecorderRef = useRef(null)
  const delayedVideoRef = useRef(null)
  const mediaSourceRef = useRef(null)
  const sourceBufferRef = useRef(null)
  const delayIntervalRef = useRef(null)
  const hiddenStreamRef = useRef(null) // 원본 트랙을 담는 숨겨진 MediaStream
  const [delayBufferReady, setDelayBufferReady] = useState(false) // 지연 버퍼 준비 완료
  const [selectedQuality, setSelectedQuality] = useState('high') // [advice from AI] 화질 선택 (기본: 고화질)

  // [advice from AI] 해시(#)로 token, url 전달 - 쿼리(?)는 ws:// 등이 Vite 403 유발
  const hashParams = new URLSearchParams(window.location.hash.slice(1))
  const searchParams = new URLSearchParams(window.location.search)
  const urlToken = hashParams.get('token') || searchParams.get('token')
  const urlWs = hashParams.get('url') || hashParams.get('ws_url') || searchParams.get('url') || searchParams.get('ws_url')
  const isReviewerFromUrl = hashParams.get('role') === 'reviewer'

  const [pendingReviewerConnect, setPendingReviewerConnect] = useState(null) // { wsUrl, token }

  useEffect(() => {
    if (urlToken && urlWs) {
      // [advice from AI] 검수자: 연결 정보만 저장, 오버레이 없이 화질 선택 UI 표시
      if (isReviewerFromUrl) {
        setStatus('화질을 선택한 후 연결 버튼을 클릭하세요.')
        setPendingReviewerConnect({ wsUrl: urlWs, token: urlToken })
        return
      }
      connectWithToken(urlWs, urlToken, isReviewerFromUrl)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const updateTracksInfo = (room) => {
    if (!room) return
    const participants = Array.from(room.remoteParticipants.values())
    const tracks = participants.flatMap((p) => Array.from(p.trackPublications.values()))
    setTracksInfo(
      `참가자: ${participants.length}명 | 트랙: ${tracks.length}개 (비디오: ${tracks.filter((t) => t.kind === 'video').length}, 오디오: ${tracks.filter((t) => t.kind === 'audio').length})`
    )
  }

  const prepare = async () => {
    setLoading(true)
    setError(null)
    setStatus('백엔드에서 Ingress/토큰 준비 중...')

    try {
      const res = await fetch(`${API_BASE}/api/prepare`)
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(err.detail || '준비 실패')
      }
      const data = await res.json()
      setPrepareData(data)
      setStatus('준비 완료. 참가자를 선택해 접속하세요.')
    } catch (err) {
      setError(err.message)
      setStatus(`오류: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }

  // [advice from AI] 검수자용 수집된 트랙 저장
  const collectedTracksRef = useRef({ video: null, audio: null })

  // [advice from AI] 검수자용 지연 재생 설정 (클라이언트 측 버퍼링)
  // 비디오와 오디오 트랙이 모두 수집된 후에만 MediaRecorder 시작
  const setupDelayedPlayback = useCallback(() => {
    const { video, audio } = collectedTracksRef.current
    console.log('[delay] 지연 재생 설정 체크', { video: !!video, audio: !!audio })

    // 이미 설정된 경우 스킵
    if (mediaRecorderRef.current) {
      console.log('[delay] MediaRecorder 이미 존재, 스킵')
      return
    }

    // 비디오와 오디오 모두 필요 (하나라도 없으면 대기)
    if (!video || !audio) {
      console.log('[delay] 트랙 대기 중...')
      return
    }

    console.log('[delay] 비디오+오디오 모두 수집됨')

    // [advice from AI] 트랙 상태 디버깅
    const videoMST = video.mediaStreamTrack
    const audioMST = audio.mediaStreamTrack
    console.log('[delay] video track:', {
      readyState: videoMST.readyState,
      enabled: videoMST.enabled,
      muted: videoMST.muted,
      kind: videoMST.kind,
    })
    console.log('[delay] audio track:', {
      readyState: audioMST.readyState,
      enabled: audioMST.enabled,
      muted: audioMST.muted,
      kind: audioMST.kind,
    })

    // [advice from AI] 비디오 트랙이 muted 상태면 unmute 대기
    const startRecorder = () => {
      // MediaStream 생성
      const stream = new MediaStream()
      stream.addTrack(videoMST)
      stream.addTrack(audioMST)
      hiddenStreamRef.current = stream
      console.log('[delay] MediaStream tracks:', stream.getTracks().map(t => `${t.kind}:${t.readyState}:muted=${t.muted}`))

      startMediaRecorder(stream)
    }

    // [advice from AI] HTMLVideoElement를 통해 captureStream() 사용 (직접 트랙 녹화가 안 되는 경우)
    // hidden video 엘리먼트에 트랙을 attach하고, captureStream()으로 녹화
    const hiddenVideo = document.createElement('video')
    hiddenVideo.style.display = 'none'
    hiddenVideo.autoplay = true
    hiddenVideo.playsInline = true
    hiddenVideo.muted = true // autoplay를 위해 muted 필요
    document.body.appendChild(hiddenVideo)
    
    // 원본 트랙을 hidden video에 연결
    const originalStream = new MediaStream()
    originalStream.addTrack(videoMST)
    originalStream.addTrack(audioMST)
    hiddenVideo.srcObject = originalStream
    
    hiddenVideo.onloadedmetadata = () => {
      console.log('[delay] hidden video loaded, starting capture')
      hiddenVideo.play().catch(e => console.warn('[delay] hidden video play:', e))
      
      // captureStream()으로 녹화용 스트림 생성
      setTimeout(() => {
        try {
          // @ts-ignore - captureStream은 표준이 아니지만 대부분의 브라우저에서 지원
          const capturedStream = hiddenVideo.captureStream ? hiddenVideo.captureStream() : hiddenVideo.mozCaptureStream()
          console.log('[delay] capturedStream tracks:', capturedStream.getTracks().map(t => `${t.kind}:${t.readyState}`))
          hiddenStreamRef.current = capturedStream
          startMediaRecorder(capturedStream, hiddenVideo)
        } catch (err) {
          console.error('[delay] captureStream 실패:', err)
        }
      }, 500) // 비디오가 재생 시작할 때까지 잠시 대기
    }
    
    hiddenVideo.onerror = (e) => console.error('[delay] hidden video error:', e)
  }, [])

  // [advice from AI] MediaRecorder 시작 (분리된 함수)
  const startMediaRecorder = useCallback((stream, hiddenVideo) => {
    if (mediaRecorderRef.current) {
      console.log('[delay] MediaRecorder 이미 존재, 스킵')
      return
    }

    // MediaRecorder mimeType 결정
    const mimeTypes = [
      'video/webm;codecs=vp9,opus',
      'video/webm;codecs=vp8,opus',
      'video/webm',
    ]
    const mimeType = mimeTypes.find((mt) => MediaRecorder.isTypeSupported(mt)) || ''
    
    // [advice from AI] 선택된 화질에 따른 비트레이트 적용
    const quality = QUALITY_OPTIONS[selectedQuality] || QUALITY_OPTIONS.high
    console.log('[delay] MediaRecorder mimeType:', mimeType, '화질:', quality.label)

    try {
      const recorder = new MediaRecorder(stream, { 
        mimeType,
        videoBitsPerSecond: quality.videoBitsPerSecond,
        audioBitsPerSecond: quality.audioBitsPerSecond,
      })
      mediaRecorderRef.current = recorder

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          delayBufferRef.current.push({ timestamp: Date.now(), blob: e.data })
          console.log('[delay] chunk:', e.data.size, 'bytes, buffer:', delayBufferRef.current.length)
        }
      }

      recorder.onerror = (e) => console.error('[delay] recorder error:', e)
      recorder.onstart = () => console.log('[delay] recorder onstart, state:', recorder.state)
      recorder.onstop = () => {
        console.log('[delay] recorder onstop')
        if (hiddenVideo && hiddenVideo.parentNode) {
          hiddenVideo.parentNode.removeChild(hiddenVideo)
        }
      }
      recorder.start(500) // 500ms 간격으로 chunk 생성
      console.log('[delay] MediaRecorder 시작, state:', recorder.state)

      // MediaSource 설정 (지연 재생용)
      const mediaSource = new MediaSource()
      mediaSourceRef.current = mediaSource

      if (delayedVideoRef.current) {
        delayedVideoRef.current.src = URL.createObjectURL(mediaSource)
      }

      mediaSource.addEventListener('sourceopen', () => {
        console.log('[delay] MediaSource sourceopen')
        try {
          const sourceBuffer = mediaSource.addSourceBuffer(mimeType || 'video/webm')
          sourceBufferRef.current = sourceBuffer

          sourceBuffer.addEventListener('error', (e) => console.error('[delay] sourceBuffer error:', e))
          sourceBuffer.addEventListener('updateend', () => {
            processDelayBuffer()
          })

          // 3.5초 지연된 chunk를 append하는 interval
          delayIntervalRef.current = setInterval(() => {
            processDelayBuffer()
          }, 200)

          setDelayBufferReady(true)
          console.log('[delay] 지연 버퍼 준비 완료')
        } catch (err) {
          console.error('[delay] sourceBuffer 생성 실패:', err)
        }
      })

      function processDelayBuffer() {
        if (!sourceBufferRef.current || sourceBufferRef.current.updating) return
        if (mediaSourceRef.current?.readyState !== 'open') return

        const now = Date.now()
        while (delayBufferRef.current.length > 0) {
          const oldest = delayBufferRef.current[0]
          if (now - oldest.timestamp >= DELAY_MS) {
            delayBufferRef.current.shift()
            oldest.blob.arrayBuffer().then((buffer) => {
              try {
                if (sourceBufferRef.current && !sourceBufferRef.current.updating && mediaSourceRef.current?.readyState === 'open') {
                  sourceBufferRef.current.appendBuffer(buffer)
                }
              } catch (err) {
                console.warn('[delay] appendBuffer error:', err)
              }
            })
            break
          } else {
            break
          }
        }
      }
    } catch (err) {
      console.error('[delay] MediaRecorder 생성 실패:', err)
    }
  }, [selectedQuality]) // [advice from AI] 화질 변경 시 재생성 가능하도록

  // [advice from AI] 지연 버퍼 정리
  const cleanupDelayedPlayback = useCallback(() => {
    if (delayIntervalRef.current) {
      clearInterval(delayIntervalRef.current)
      delayIntervalRef.current = null
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    mediaRecorderRef.current = null
    if (mediaSourceRef.current && mediaSourceRef.current.readyState === 'open') {
      try {
        mediaSourceRef.current.endOfStream()
      } catch (e) { /* ignore */ }
    }
    mediaSourceRef.current = null
    sourceBufferRef.current = null
    delayBufferRef.current = []
    hiddenStreamRef.current = null
    collectedTracksRef.current = { video: null, audio: null }
    setDelayBufferReady(false)
  }, [])

  const connectWithToken = async (wsUrl, token, isReviewer = false) => {
    setStatus('룸 접속 중...')
    if (isReviewer) console.log('[reviewer] 검수자 모드로 접속 (클라이언트 측 3.5초 지연)')

    try {
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        autoSubscribe: true,
        webAudioMix: false,
      })
      roomRef.current = room

      room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
        setStatus(`연결됨 | ${participant.identity}의 트랙 구독: ${track.kind}`)
        console.log(`[track] subscribed: ${participant.identity} ${track.kind}`)

        // [advice from AI] 검수자: 실시간 소스만 구독하고 클라이언트 측 지연 재생
        if (isReviewer) {
          if (participant.identity !== REALTIME_IDENTITY) {
            console.log('[reviewer] 실시간 외 소스 구독 해제:', participant.identity)
            publication.setSubscribed(false)
            return
          }
          // 실시간 소스 트랙 → ref에 저장
          if (track.kind === Track.Kind.Video) {
            collectedTracksRef.current.video = track
            console.log('[reviewer] 비디오 트랙 수집')
          } else if (track.kind === Track.Kind.Audio) {
            collectedTracksRef.current.audio = track
            console.log('[reviewer] 오디오 트랙 수집')
          }
          // 비디오와 오디오 모두 수집되면 지연 재생 시작
          setupDelayedPlayback()
          updateTracksInfo(room)
          return
        }

        // 참가자(속기사): 실시간 표시
        const container = videoContainerRef.current
        if (!container) return

        if (track.kind === Track.Kind.Video) {
          const element = track.attach()
          element.style.width = '100%'
          container.appendChild(element)
        } else if (track.kind === Track.Kind.Audio) {
          const element = track.attach()
          document.body.appendChild(element)
          element.muted = false
          element.volume = 1.0
          audioElementsRef.current.push(element)
          setHasAudioTracks(true)
          console.log('[audio] attached:', participant.identity, {
            elements: audioElementsRef.current.length,
            canPlayback: room.canPlaybackAudio,
          })
          if (!room.canPlaybackAudio) {
            setShowAudioUnlock(true)
          } else {
            element.play().catch((e) => console.warn('[audio] attach play:', e))
          }
        }
        updateTracksInfo(room)
      })

      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        track.detach().forEach((el) => {
          el.remove()
          audioElementsRef.current = audioElementsRef.current.filter((e) => e !== el)
        })
        setHasAudioTracks(audioElementsRef.current.length > 0)
        updateTracksInfo(room)
      })

      room.on(RoomEvent.AudioPlaybackStatusChanged, () => {
        if (!room.canPlaybackAudio) {
          setShowAudioUnlock(true)
        }
      })

      room.on(RoomEvent.Disconnected, () => {
        setStatus('연결 해제됨')
        setIsConnected(false)
        setHasAudioTracks(false)
        setShowAudioUnlock(false)
        audioElementsRef.current = []
        if (videoContainerRef.current) {
          videoContainerRef.current.innerHTML = ''
        }
        setTracksInfo('')
        // [advice from AI] 검수자 지연 버퍼 정리
        cleanupDelayedPlayback()
      })

      room.on(RoomEvent.Connected, () => {
        setStatus(`연결됨 | Room: ${room.name} | ${room.localParticipant.identity}`)
        setIsConnected(true)
        const participants = Array.from(room.remoteParticipants.values()).map((p) => p.identity)
        console.log('[room] 참가자:', participants)
        // [advice from AI] 검수자: 실시간 소스만 구독 (클라이언트 측 지연 적용)
        if (isReviewer) {
          room.remoteParticipants.forEach((p) => {
            if (p.identity !== REALTIME_IDENTITY) {
              p.trackPublications.forEach((pub) => pub.setSubscribed(false))
              console.log('[reviewer] 실시간 외 소스 구독 해제:', p.identity)
            }
          })
        }
        updateTracksInfo(room)
      })

      room.on(RoomEvent.TrackPublished, (publication, participant) => {
        // [advice from AI] 검수자: 실시간 외 소스는 구독하지 않음
        if (isReviewer && participant.identity !== REALTIME_IDENTITY) {
          publication.setSubscribed(false)
        }
      })

      room.on(RoomEvent.ParticipantConnected, (participant) => {
        // [advice from AI] 검수자: 실시간 외 참가자 트랙 구독 해제
        if (isReviewer && participant.identity !== REALTIME_IDENTITY) {
          participant.trackPublications.forEach((pub) => pub.setSubscribed(false))
          console.log('[reviewer] 새 참가자 구독 해제:', participant.identity)
        }
      })

      await room.connect(wsUrl, token)
    } catch (err) {
      setStatus(`오류: ${err.message}`)
      setError(err.message)
      console.error(err)
    }
  }

  const joinAsParticipant = (participant, isReviewer = false) => {
    if (!participant?.token) return
    const wsUrl = prepareData.ws_url
    const baseUrl = window.location.origin + window.location.pathname
    let joinUrl = `${baseUrl}#url=${encodeURIComponent(wsUrl)}&token=${encodeURIComponent(participant.token)}`
    if (isReviewer) joinUrl += '&role=reviewer'
    window.open(joinUrl, '_blank', 'noopener,noreferrer')
  }

  const joinInCurrentTab = (participant) => {
    if (!participant?.token) return
    const isReviewer = participant.identity === 'reviewer'
    connectWithToken(prepareData.ws_url, participant.token, isReviewer)
  }

  const disconnect = () => {
    if (roomRef.current) {
      roomRef.current.disconnect()
      roomRef.current = null
    }
    cleanupDelayedPlayback()
  }

  // [advice from AI] 브라우저 autoplay 정책: 사용자 클릭 후 오디오 재생 (반드시 클릭 이벤트 핸들러 내에서 호출)
  const enableAudio = async () => {
    // [advice from AI] 연결 전 대기 중: 접속만 하고, 오디오는 아래 오버레이 클릭으로 활성화 (await 후 사용자 제스처 소진됨)
    if (pendingReviewerConnect) {
      const { wsUrl, token } = pendingReviewerConnect
      setShowAudioUnlock(false)
      setPendingReviewerConnect(null)
      try {
        await connectWithToken(wsUrl, token, true)
        // [advice from AI] await 후 사용자 제스처 소진 → 오버레이 표시, 사용자가 "오디오 활성화" 클릭 시 재생
        setShowAudioUnlock(true)
      } catch (e) {
        console.warn('[audio] connect error:', e)
      }
      return
    }

    const room = roomRef.current
    console.log('[audio] enableAudio called, elements=', audioElementsRef.current.length)
    if (room) {
      try {
        await room.startAudio()
        setShowAudioUnlock(false)
        console.log('[audio] startAudio ok, canPlayback=', room.canPlaybackAudio)
      } catch (e) {
        console.warn('[audio] startAudio error:', e)
      }
    }
    audioElementsRef.current.forEach((el, i) => {
      el.muted = false
      el.volume = 1.0
      const srcObj = el.srcObject
      const audioTracks = srcObj?.getAudioTracks?.() || []
      console.log('[audio] element', i, 'before play:', {
        paused: el.paused,
        muted: el.muted,
        volume: el.volume,
        srcObject: !!srcObj,
        audioTracksCount: audioTracks.length,
        trackState: audioTracks[0]?.readyState,
        trackEnabled: audioTracks[0]?.enabled,
        trackMuted: audioTracks[0]?.muted,
      })
      el.play()
        .then(() => console.log('[audio] element', i, 'play ok, paused=', el.paused))
        .catch((e) => console.warn('[audio] element', i, 'play failed:', e))
    })
  }

  // [advice from AI] 검수자 지연 비디오 재생 시작
  const playDelayedVideo = () => {
    if (delayedVideoRef.current) {
      delayedVideoRef.current.play().catch((e) => console.warn('[delay] play error:', e))
    }
  }

  // 이미 token/url로 열린 참가자 탭: 뷰어만 표시
  if (urlToken && urlWs) {
    return (
      <div className="app">
        {/* [advice from AI] 검수자가 아닌 경우에만 오디오 활성화 오버레이 표시 */}
        {showAudioUnlock && !isReviewerFromUrl && (
          <div
            className="audio-unlock-overlay"
            onClick={enableAudio}
            onKeyDown={(e) => e.key === 'Enter' && enableAudio()}
            role="button"
            tabIndex={0}
          >
            <div className="audio-unlock-content">
              <p>🔊 오디오 활성화</p>
              <p className="audio-unlock-hint">
                브라우저 정책상 사용자 클릭이 필요합니다. 아래 버튼을 클릭하세요.
              </p>
              <button type="button" className="btn-audio-unlock" onClick={(e) => { e.stopPropagation(); enableAudio(); }}>
                오디오 활성화
              </button>
            </div>
          </div>
        )}
        <h1>HLS 동기화 테스트 - {isReviewerFromUrl ? '검수자 (3.5초 지연)' : '참가자'} 뷰어</h1>
        {isReviewerFromUrl && delayBufferReady && (
          <div className="info-banner">
            ✅ 클라이언트 측 3.5초 지연 버퍼 활성화됨
          </div>
        )}
        {/* [advice from AI] 검수자용 화질 선택 + 연결 버튼 (연결 전에만 표시) */}
        {isReviewerFromUrl && pendingReviewerConnect && !isConnected && (
          <div className="connect-panel">
            <div className="quality-selector">
              <label htmlFor="quality-select">화질 선택: </label>
              <select
                id="quality-select"
                value={selectedQuality}
                onChange={(e) => setSelectedQuality(e.target.value)}
              >
                {Object.entries(QUALITY_OPTIONS).map(([key, opt]) => (
                  <option key={key} value={key}>{opt.label}</option>
                ))}
              </select>
            </div>
            <button type="button" className="btn-connect" onClick={enableAudio}>
              🔗 연결하기
            </button>
          </div>
        )}
        <div className={`status ${isConnected ? 'connected' : ''}`}>{status}</div>
        {/* [advice from AI] 검수자: 지연 비디오 표시 / 참가자: 실시간 비디오 */}
        {isReviewerFromUrl ? (
          <div className="video-container">
            <video
              ref={delayedVideoRef}
              autoPlay
              playsInline
              muted={false}
              style={{ width: '100%' }}
            />
          </div>
        ) : (
          <div className="video-container" ref={videoContainerRef} />
        )}
        {tracksInfo && <div className="tracks-info">{tracksInfo}</div>}
        <div className="viewer-buttons">
          {isReviewerFromUrl ? (
            <button
              type="button"
              className="btn-enable-audio"
              onClick={playDelayedVideo}
              disabled={!delayBufferReady}
            >
              🔊 지연 영상 재생 {!delayBufferReady && '(버퍼링 중...)'}
            </button>
          ) : (
            <button
              type="button"
              className="btn-enable-audio"
              onClick={enableAudio}
              disabled={!isConnected}
            >
              🔊 오디오 재생 {!hasAudioTracks && '(트랙 대기 중)'}
            </button>
          )}
          <button className="btn-disconnect" onClick={disconnect} disabled={!isConnected}>
            접속 해제
          </button>
        </div>
      </div>
    )
  }

  // 메인 화면: 준비 + 참가자 선택
  return (
    <div className="app">
      <h1>HLS 동기화 테스트</h1>
      <p className="subtitle">백엔드에서 Ingress 생성 및 토큰을 준비한 뒤, 참가자로 룸에 입장합니다.</p>

      {!prepareData ? (
        <div className="prepare-section">
          <button onClick={prepare} disabled={loading}>
            {loading ? '준비 중...' : '테스트 시작'}
          </button>
          {error && <p className="error">{error}</p>}
        </div>
      ) : (
        <div className="participants-section">
          <p className="status-text">{status}</p>
          <div className="participant-buttons">
            <div className="participant-row">
              <span>참가자 1</span>
              <button onClick={() => joinInCurrentTab(prepareData.participants[0])}>
                이 탭에서 접속
              </button>
            </div>
            <div className="participant-row">
              <span>참가자 2</span>
              <button onClick={() => joinAsParticipant(prepareData.participants[1])}>
                새 탭에서 접속
              </button>
            </div>
            <div className="participant-row">
              <span>참가자 3</span>
              <button onClick={() => joinAsParticipant(prepareData.participants[2])}>
                새 탭에서 접속
              </button>
            </div>
            {(() => {
              const reviewer = prepareData.participants?.find((p) => p.identity === 'reviewer')
              if (!reviewer) return null
              return (
                <div className="participant-row participant-row-reviewer">
                  <span>검수자 (3~4초 지연 영상)</span>
                  <button onClick={() => joinInCurrentTab(reviewer)}>이 탭에서 접속</button>
                  <button onClick={() => joinAsParticipant(reviewer, true)}>새 탭에서 접속</button>
                </div>
              )
            })()}
          </div>
        </div>
      )}

      {showAudioUnlock && isConnected && (
        <div
          className="audio-unlock-overlay"
          onClick={enableAudio}
          onKeyDown={(e) => e.key === 'Enter' && enableAudio()}
          role="button"
          tabIndex={0}
        >
          <div className="audio-unlock-content">
            <p>🔊 오디오가 재생되지 않습니다</p>
            <p className="audio-unlock-hint">아래 버튼을 클릭하여 오디오를 활성화하세요</p>
            <button type="button" className="btn-audio-unlock" onClick={(e) => { e.stopPropagation(); enableAudio(); }}>
              오디오 활성화
            </button>
          </div>
        </div>
      )}
      {(isConnected || prepareData) && (
        <>
          <div className={`status ${isConnected ? 'connected' : ''}`}>{status}</div>
          <div className="video-container" ref={videoContainerRef} />
          {tracksInfo && <div className="tracks-info">{tracksInfo}</div>}
          {isConnected && (
            <div className="viewer-buttons">
              <button
                type="button"
                className="btn-enable-audio"
                onClick={enableAudio}
                disabled={!isConnected}
              >
                🔊 오디오 재생 {!hasAudioTracks && '(트랙 대기 중)'}
              </button>
              <button className="btn-disconnect" onClick={disconnect}>
                접속 해제
              </button>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default App
