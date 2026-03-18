/**
 * [advice from AI] Webfos 메인 앱 컴포넌트
 *
 * 플로우:
 * 1. 채널 목록 조회
 * 2. 채널 선택 (입장 버튼)
 * 3. "참가자로 참여" / "검수자로 참여" 선택 -> 현재 탭에서 바로 연결
 * 
 * [advice from AI] 클라이언트 측 버퍼링 사용:
 * - 검수자: DelayedPlayer 사용 (클라이언트 측 지연 버퍼링)
 * - 참가자: VideoPlayer 사용 (실시간 재생)
 */

import { useState, useCallback, useEffect, useRef } from 'react'
import { useLiveKit } from './hooks/useLiveKit'
import { VideoPlayer } from './components/VideoPlayer'
import { DelayedPlayer } from './components/DelayedPlayer'
import { DelaySelector } from './components/DelaySelector'
import { ConnectionPanel } from './components/ConnectionPanel'
import { StenographerPanel } from './components/StenographerPanel'
import { BroadcastPanel } from './components/BroadcastPanel'
import { listChannels, joinChannel } from './api/roomApi'
import { DEFAULT_DELAY_SECONDS } from './utils/constants'

function App() {
  const [channels, setChannels] = useState([])
  const [selectedChannel, setSelectedChannel] = useState(null)
  const [currentRole, setCurrentRole] = useState(null)
  const [selectedDelay, setSelectedDelay] = useState(DEFAULT_DELAY_SECONDS)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  // [advice from AI] 턴 관리 상태
  const [stenographers, setStenographers] = useState([])  // [{ identity, text }]
  const [currentTurnHolder, setCurrentTurnHolder] = useState(null)
  const [broadcastText, setBroadcastText] = useState('')
  const [myText, setMyText] = useState('')  // 내 입력 텍스트 (로컬 관리)
  
  // [advice from AI] STT 상태
  const [sttEnabled, setSttEnabled] = useState(false)
  const [sttPartialText, setSttPartialText] = useState('')  // 레거시 호환
  
  // [advice from AI] STT 편집 모드 상태
  const [editMode, setEditMode] = useState(false)           // 편집 모드 여부 (UI 렌더링용)
  const editModeRef = useRef(false)                         // [advice from AI] 편집 모드 ref (콜백에서 최신값 참조용)
  const currentTurnHolderRef = useRef(null)                 // [advice from AI] 턴 보유자 ref (콜백에서 최신값 참조용)
  const [sttConfirmedText, setSttConfirmedText] = useState('')  // 확정된 STT 텍스트
  const [sttTypingText, setSttTypingText] = useState('')    // 입력 중 STT 텍스트

  const isReviewer = currentRole === 'reviewer'

  const {
    connectionState,
    isConnected,
    participants,
    videoTrack,
    audioTrack,
    connect,
    disconnect,
    startAudio,
    // [advice from AI] 턴 관리용 추가
    localIdentity,
    sendData,
    onDataReceived,
  } = useLiveKit({ isReviewer })

  useEffect(() => {
    loadChannels()
  }, [])

  // [advice from AI] DataChannel 메시지 수신 처리
  // 의존성에서 myText 제거 - 클로저 문제 방지, setStenographers 콜백에서 최신 상태 사용
  useEffect(() => {
    if (!isConnected || isReviewer) return
    
    const unsubscribe = onDataReceived((message, senderIdentity) => {
      console.log('[App] DataChannel 메시지:', message.type, message)
      
      // [advice from AI] 백엔드 메시지에 sender 필드가 있으면 사용
      const actualSender = message.sender || senderIdentity
      
      switch (message.type) {
        case 'stenographer.list':
          // [advice from AI] 속기사 목록 동기화
          // setStenographers 콜백에서 이전 상태와 myText 최신값 사용
          setStenographers(prev => {
            const newList = message.stenographers || []
            return newList.map(s => {
              if (s.identity === localIdentity) {
                // 내 텍스트는 로컬 상태 유지 (prev에서 찾거나 빈 문자열)
                const myPrevText = prev.find(p => p.identity === localIdentity)?.text || ''
                return { ...s, text: myPrevText }
              }
              return s
            })
          })
          console.log('[App] 속기사 목록 업데이트:', message.stenographers?.length, '명')
          break
          
        case 'turn.grant':
        case 'turn.switch':
          // 턴 권한 변경
          currentTurnHolderRef.current = message.holder  // [advice from AI] ref 먼저 업데이트 (동기적)
          setCurrentTurnHolder(message.holder)
          
          // [advice from AI] 내가 새 턴 보유자가 되면 텍스트/편집 상태 초기화
          // 이전 턴 보유자의 STT 텍스트가 넘어오지 않도록 깨끗한 상태에서 시작
          if (message.holder === localIdentity) {
            setMyText('')
            editModeRef.current = false
            setEditMode(false)
            setSttConfirmedText('')
            setSttTypingText('')
            console.log('[App] 내가 새 턴 보유자 - 텍스트/편집 상태 초기화')
          }
          console.log('[App] 턴 보유자 변경:', message.holder)
          break
          
        case 'caption.broadcast':
          // 송출 텍스트 수신
          setBroadcastText(message.text || '')
          // [advice from AI] 송출자의 입력란 초기화 (자신이 송출한 경우)
          if (actualSender === localIdentity) {
            setMyText('')
          }
          break
          
        case 'caption.draft':
          // [advice from AI] 다른 속기사의 임시 텍스트 업데이트
          if (actualSender !== localIdentity) {
            setStenographers(prev => prev.map(s => 
              s.identity === actualSender 
                ? { ...s, text: message.text }
                : s
            ))
          }
          break
        
        // [advice from AI] STT 결과 수신 → 텍스트 입력창에 append
        case 'stt.partial':
          setSttPartialText(message.text || '')
          console.log('[App] STT partial:', message.text?.substring(0, 50))
          break
          
        case 'stt.final':
          // [advice from AI] 최종 결과를 내 텍스트에 append
          if (message.text) {
            setMyText(prev => prev + message.text)
            // 속기사 목록에도 반영
            setStenographers(prev => prev.map(s =>
              s.identity === localIdentity
                ? { ...s, text: s.text + message.text }
                : s
            ))
          }
          setSttPartialText('')  // 파셜 클리어
          console.log('[App] STT final appended:', message.text?.substring(0, 50))
          break
          
        case 'stt.status':
          // [advice from AI] STT 상태 업데이트
          setSttEnabled(message.enabled || false)
          console.log('[App] STT status:', message.enabled, message.message)
          break
        
        case 'stt.text':
          // [advice from AI] RoomAgent가 턴 보유자에게만 전송하는 STT 텍스트 수신
          // 편집 모드가 아닐 때만 업데이트 (편집 중이면 STT 텍스트 무시)
          if (!editModeRef.current) {
            setSttConfirmedText(message.confirmed || '')
            setSttTypingText(message.typing || '')
            // myText도 동기화 (확정 + 입력 중)
            setMyText((message.confirmed || '') + (message.typing || ''))
            // 속기사 목록에도 반영
            setStenographers(prev => prev.map(s =>
              s.identity === localIdentity
                ? { ...s, text: (message.confirmed || '') + (message.typing || '') }
                : s
            ))
          }
          console.log('[App] STT text:', message.confirmed?.length, message.typing?.length, 'editMode:', editModeRef.current)
          break
        
        case 'edit.status':
          // [advice from AI] 편집 모드 상태 업데이트 (다른 속기사가 편집 중인지)
          console.log('[App] Edit status:', message.editing, message.editor)
          break
          
        default:
          console.log('[App] 알 수 없는 메시지 타입:', message.type)
      }
    })
    
    // [advice from AI] 연결 후 백엔드에 상태 요청 (초기 메시지 손실 방지)
    // 약간의 지연 후 요청하여 콜백이 확실히 등록된 후 응답 수신
    const requestTimer = setTimeout(() => {
      console.log('[App] 백엔드에 상태 요청')
      sendData({ type: 'state.request' })
    }, 100)
    
    return () => {
      clearTimeout(requestTimer)
      unsubscribe()
    }
  }, [isConnected, isReviewer, onDataReceived, localIdentity, sendData])  // [advice from AI] editMode 제거 - ref 사용으로 의존성 불필요

  const loadChannels = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await listChannels()
      setChannels(data.channels || [])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  // [advice from AI] connect에 isReviewer를 인자로 전달 (setState 비동기 문제 해결)
  const handleJoinAs = useCallback(async (channelId, role) => {
    setLoading(true)
    setError(null)
    try {
      const data = await joinChannel(channelId, role)
      const isReviewerRole = role === 'reviewer'
      setCurrentRole(role)
      setSelectedChannel(channels.find(ch => ch.id === channelId))
      await connect(data.ws_url, data.token, isReviewerRole)
    } catch (err) {
      setError(err.message)
      setCurrentRole(null)
    } finally {
      setLoading(false)
    }
  }, [channels, connect])

  const handleDisconnect = useCallback(() => {
    disconnect()
    setSelectedChannel(null)
    setCurrentRole(null)
    setStenographers([])
    currentTurnHolderRef.current = null  // [advice from AI] ref 초기화
    setCurrentTurnHolder(null)
    setBroadcastText('')
    setMyText('')
    setSttEnabled(false)
    setSttPartialText('')
    editModeRef.current = false  // [advice from AI] ref 초기화
    setEditMode(false)
    setSttConfirmedText('')
    setSttTypingText('')
  }, [disconnect])

  // [advice from AI] STT 토글 핸들러
  const handleSttToggle = useCallback(() => {
    if (sttEnabled) {
      sendData({ type: 'stt.stop' })
    } else {
      sendData({ type: 'stt.start' })
    }
  }, [sttEnabled, sendData])

  // [advice from AI] 속기사 텍스트 변경 핸들러
  const handleTextChange = useCallback((identity, text) => {
    // [advice from AI] 본인 패널만 수정 가능
    if (identity !== localIdentity) {
      console.warn('[App] 다른 속기사 패널 수정 시도 무시:', identity)
      return
    }
    
    // 본인 텍스트 로컬 상태 업데이트
    setMyText(text)
    
    // 로컬 속기사 목록에도 업데이트 (내 패널 표시용)
    setStenographers(prev => prev.map(s => 
      s.identity === identity ? { ...s, text } : s
    ))
    
    // 다른 참가자에게 브로드캐스트
    sendData({ type: 'caption.draft', text })
  }, [sendData, localIdentity])

  // [advice from AI] 송출 버튼 핸들러
  // 프론트엔드는 수동적 - RoomAgent의 broadcast 응답을 기다림
  const handleBroadcast = useCallback((identity, text) => {
    console.log('[App] 송출 요청:', identity, text)
    
    // 백엔드로 송출 요청만 전송
    // 모든 상태 업데이트는 RoomAgent의 broadcast 응답에서 처리
    sendData({ type: 'caption.broadcast', text })
  }, [sendData])
  
  // [advice from AI] 편집 모드 시작 핸들러 (포커스 시)
  const handleEditStart = useCallback(() => {
    if (!sttEnabled) return  // STT가 꺼져있으면 편집 모드 의미 없음
    if (editModeRef.current) return  // 이미 편집 모드면 무시
    
    console.log('[App] 편집 모드 시작')
    editModeRef.current = true  // [advice from AI] ref 먼저 업데이트 (동기적)
    setEditMode(true)           // state 업데이트 (UI 렌더링용)
    sendData({ type: 'edit.start' })
  }, [sttEnabled, sendData])
  
  // [advice from AI] 편집 모드 종료 핸들러 (F2 키 입력 시)
  const handleEditEnd = useCallback((editedText) => {
    if (!editModeRef.current) return  // ref로 체크 (최신값)
    
    console.log('[App] 편집 모드 종료, 텍스트 병합 요청:', editedText?.length)
    editModeRef.current = false  // [advice from AI] ref 먼저 업데이트 (동기적)
    setEditMode(false)           // state 업데이트 (UI 렌더링용)
    sendData({ type: 'edit.end', text: editedText })
  }, [sendData])

  // ===== 연결된 상태 — 검수자 뷰 =====
  // [advice from AI] 검수자: 지연 영상 + 자막 검수용 (추후 구현)
  if (isConnected && isReviewer) {
    return (
      <div className="app">
        <h1>Webfos - 검수자 ({selectedDelay}초 지연)</h1>
        {selectedChannel && <p className="channel-name">{selectedChannel.name}</p>}

        <DelaySelector
          value={selectedDelay}
          onChange={setSelectedDelay}
        />

        <DelayedPlayer
          videoTrack={videoTrack}
          audioTrack={audioTrack}
          delay={selectedDelay}
        />

        <ConnectionPanel
          connectionState={connectionState}
          participants={participants}
          onDisconnect={handleDisconnect}
          isReviewer={true}
        />
      </div>
    )
  }

  // ===== 연결된 상태 — 참가자(속기사) 뷰 =====
  // [advice from AI] 레이아웃: 비디오(1/3) | 속기사패널(2개) | 송출텍스트
  if (isConnected && !isReviewer) {
    // [advice from AI] 속기사 목록이 비어있으면 기본값 설정 (백엔드 연동 전)
    const displayStenographers = stenographers.length > 0 
      ? stenographers 
      : [
          { identity: localIdentity || 'me', text: '' },
          { identity: 'waiting...', text: '' },
        ]
    
    // [advice from AI] 송출 권한 로직 개선
    // - 백엔드에서 turn.grant를 받기 전까지는 아무도 턴을 갖지 않음
    // - currentTurnHolder가 null이면 모든 송출 버튼 비활성화
    // - 백엔드가 항상 1명에게 턴을 부여하므로 정상 연결 시 null이 오래 지속되지 않음
    const activeTurnHolder = currentTurnHolder
    
    return (
      <div className="app stenographer-view">
        {/* 상단 상태바 */}
        <div className="status-bar">
          <span className="status-title">Webfos - 속기사</span>
          <span className="status-channel">{selectedChannel?.name}</span>
          <span className="status-identity">내 ID: {localIdentity?.slice(0, 8) || '...'}</span>
          <button className="btn-audio" onClick={startAudio}>
            🔊 오디오 시작
          </button>
          <button 
            className={`btn-stt ${sttEnabled ? 'active' : ''}`} 
            onClick={handleSttToggle}
          >
            {sttEnabled ? '🎤 STT 중지' : '🎤 STT 시작'}
          </button>
          <button className="btn-disconnect" onClick={handleDisconnect}>
            연결 해제
          </button>
        </div>

        {/* 메인 콘텐츠 영역 */}
        <div className="main-content">
          {/* 좌측: 비디오 플레이어 (1/3) */}
          <div className="video-section">
            <VideoPlayer
              videoTrack={videoTrack}
              audioTrack={audioTrack}
            />
          </div>

          {/* 중앙: 속기사 패널 (2개 세로 배치) */}
          <div className="stenographer-section">
            {displayStenographers.slice(0, 2).map((steno, idx) => {
              const isMyPanel = steno.identity === localIdentity
              return (
                <StenographerPanel
                  key={steno.identity}
                  identity={steno.identity}
                  index={idx + 1}
                  text={isMyPanel ? myText : steno.text}
                  isMyPanel={isMyPanel}
                  hasTurn={steno.identity === activeTurnHolder}
                  editMode={isMyPanel && editMode}
                  onTextChange={(text) => handleTextChange(steno.identity, text)}
                  onBroadcast={(text) => handleBroadcast(steno.identity, text)}
                  onEditStart={handleEditStart}
                  onEditEnd={handleEditEnd}
                />
              )
            })}
          </div>

          {/* 우측: 송출 텍스트 패널 */}
          <div className="broadcast-section">
            <BroadcastPanel text={broadcastText} />
            
            {/* [advice from AI] STT 실시간 결과 표시 (파셜만 - final은 입력창에 자동 추가) */}
            {sttEnabled && (
              <div className="stt-section">
                <h4>🎤 STT 실시간</h4>
                {sttPartialText ? (
                  <p className="stt-partial">{sttPartialText}</p>
                ) : (
                  <p className="stt-empty">음성 인식 대기...</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ===== 메인 화면 (채널 선택 + 역할 선택) =====
  return (
    <div className="app">
      <h1>Webfos - 채널 선택</h1>
      <p className="subtitle">시청할 채널을 선택하세요.</p>

      {error && <p className="error">{error}</p>}

      {/* 채널 목록 */}
      {!selectedChannel && (
        <div className="channel-list">
          {loading && <p>채널 목록 로딩 중...</p>}

          {channels.map((channel) => (
            <div key={channel.id} className={`channel-card ${!channel.is_active ? 'inactive' : ''}`}>
              <div className="channel-info">
                <h3>{channel.name} {channel.is_active ? '' : ''}</h3>
                <p>{channel.description}</p>
              </div>
              <button
                onClick={() => setSelectedChannel(channel)}
                disabled={loading || !channel.is_active}
              >
                {channel.is_active ? '입장' : '비활성'}
              </button>
            </div>
          ))}

          {!loading && channels.length === 0 && (
            <p className="no-channels">채널이 없습니다.</p>
          )}
        </div>
      )}

      {/* 역할 선택 (채널 선택 후, 연결 전) */}
      {selectedChannel && !isConnected && (
        <div className="role-selection">
          <div className="selected-channel">
            <h2>{selectedChannel.name}</h2>
            <button className="btn-back" onClick={() => { setSelectedChannel(null); setError(null); }}>
              채널 목록으로
            </button>
          </div>

          <p className="role-hint">역할을 선택하여 접속하세요.</p>

          <div className="role-buttons">
            <button
              className="btn-join participant"
              onClick={() => handleJoinAs(selectedChannel.id, 'participant')}
              disabled={loading}
            >
              {loading ? '연결 중...' : '참가자로 참여'}
            </button>

            <button
              className="btn-join reviewer"
              onClick={() => handleJoinAs(selectedChannel.id, 'reviewer')}
              disabled={loading}
            >
              {loading ? '연결 중...' : '검수자로 참여'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
