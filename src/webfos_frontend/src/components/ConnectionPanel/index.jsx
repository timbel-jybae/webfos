/**
 * 연결 패널 컴포넌트
 * 
 * 연결 상태 표시, 연결/해제 버튼, 참가자 정보.
 */

import { CONNECTION_STATE } from '../../utils/constants'
import './styles.css'

export function ConnectionPanel({
  connectionState,
  participants = [],
  onConnect,
  onDisconnect,
  onStartAudio,
  isReviewer = false,
  children,
}) {
  const isConnected = connectionState === CONNECTION_STATE.CONNECTED
  const isConnecting = connectionState === CONNECTION_STATE.CONNECTING
  
  const getStatusText = () => {
    switch (connectionState) {
      case CONNECTION_STATE.CONNECTED:
        return '연결됨'
      case CONNECTION_STATE.CONNECTING:
        return '연결 중...'
      case CONNECTION_STATE.RECONNECTING:
        return '재연결 중...'
      default:
        return '연결 안됨'
    }
  }
  
  const getStatusClass = () => {
    switch (connectionState) {
      case CONNECTION_STATE.CONNECTED:
        return 'status-connected'
      case CONNECTION_STATE.CONNECTING:
      case CONNECTION_STATE.RECONNECTING:
        return 'status-connecting'
      default:
        return 'status-disconnected'
    }
  }
  
  return (
    <div className="connection-panel">
      <div className={`status-indicator ${getStatusClass()}`}>
        <span className="status-dot" />
        <span>{getStatusText()}</span>
      </div>
      
      {/* 추가 컨텐츠 (화질 선택 등) */}
      {children}
      
      <div className="button-group">
        {!isConnected ? (
          <button
            className="btn-connect"
            onClick={onConnect}
            disabled={isConnecting}
          >
            {isConnecting ? '연결 중...' : '연결하기'}
          </button>
        ) : (
          <>
            {!isReviewer && (
              <button className="btn-audio" onClick={onStartAudio}>
                🔊 오디오 재생
              </button>
            )}
            <button className="btn-disconnect" onClick={onDisconnect}>
              연결 해제
            </button>
          </>
        )}
      </div>
      
      {isConnected && participants.length > 0 && (
        <div className="participants-info">
          참가자: {participants.map(p => p.name || p.identity).join(', ')}
        </div>
      )}
    </div>
  )
}

export default ConnectionPanel
