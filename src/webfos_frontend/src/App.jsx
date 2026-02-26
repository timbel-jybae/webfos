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

import { useState, useCallback, useEffect } from 'react'
import { useLiveKit } from './hooks/useLiveKit'
import { VideoPlayer } from './components/VideoPlayer'
import { DelayedPlayer } from './components/DelayedPlayer'
import { QualitySelector } from './components/QualitySelector'
import { ConnectionPanel } from './components/ConnectionPanel'
import { listChannels, joinChannel } from './api/roomApi'
import { DELAY_MS } from './utils/constants'

function App() {
  const [channels, setChannels] = useState([])
  const [selectedChannel, setSelectedChannel] = useState(null)
  const [currentRole, setCurrentRole] = useState(null)
  const [selectedQuality, setSelectedQuality] = useState('high')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

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
  } = useLiveKit({ isReviewer })

  useEffect(() => {
    loadChannels()
  }, [])

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

  const handleJoinAs = useCallback(async (channelId, role) => {
    setLoading(true)
    setError(null)
    try {
      const data = await joinChannel(channelId, role)
      setCurrentRole(role)
      setSelectedChannel(channels.find(ch => ch.id === channelId))
      await connect(data.ws_url, data.token)
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
  }, [disconnect])

  // ===== 연결된 상태 — 검수자 뷰 =====
  // [advice from AI] 클라이언트 측 지연 버퍼링 사용 (DelayedPlayer)
  if (isConnected && isReviewer) {
    return (
      <div className="app">
        <h1>Webfos - 검수자 ({DELAY_MS / 1000}초 지연)</h1>
        {selectedChannel && <p className="channel-name">{selectedChannel.name}</p>}

        <QualitySelector
          value={selectedQuality}
          onChange={setSelectedQuality}
        />

        <DelayedPlayer
          videoTrack={videoTrack}
          audioTrack={audioTrack}
          quality={selectedQuality}
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

  // ===== 연결된 상태 — 참가자 뷰 =====
  if (isConnected && !isReviewer) {
    return (
      <div className="app">
        <h1>Webfos - 참가자</h1>
        {selectedChannel && <p className="channel-name">{selectedChannel.name}</p>}

        <VideoPlayer
          videoTrack={videoTrack}
          audioTrack={audioTrack}
        />

        <ConnectionPanel
          connectionState={connectionState}
          participants={participants}
          onDisconnect={handleDisconnect}
          onStartAudio={startAudio}
        />
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
