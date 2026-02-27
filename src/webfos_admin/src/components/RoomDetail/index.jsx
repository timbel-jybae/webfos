import ParticipantList from '../ParticipantList'
import './styles.css'

function RoomDetail({ roomName, detail, onClose }) {
  const participants = detail?.participants || []
  const agentState = detail?.agent_state
  const broadcastHistory = detail?.broadcast_history || []
  
  return (
    <div className="room-detail">
      <div className="room-detail-header">
        <h2>{roomName}</h2>
        <button className="btn-close" onClick={onClose}>✕</button>
      </div>
      
      <div className="room-detail-body">
        <div className="detail-section">
          <h3>룸 정보</h3>
          <div className="detail-grid">
            <div className="detail-item">
              <span className="detail-label">SID</span>
              <span className="detail-value">{detail?.sid || '-'}</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">참가자</span>
              <span className="detail-value">{participants.length}명</span>
            </div>
            <div className="detail-item">
              <span className="detail-label">생성일</span>
              <span className="detail-value">
                {detail?.created_at 
                  ? new Date(detail.created_at).toLocaleString('ko-KR')
                  : '-'
                }
              </span>
            </div>
          </div>
        </div>
        
        <div className="detail-section">
          <h3>참가자 목록</h3>
          {participants.length === 0 ? (
            <div className="empty-participants">
              참가자가 없습니다.
            </div>
          ) : (
            <ParticipantList participants={participants} />
          )}
        </div>
        
        <div className="detail-section">
          <h3>RoomAgent 상태</h3>
          {agentState ? (
            <div className="agent-state">
              <div className="state-item">
                <span className="state-label">턴 보유자</span>
                <span className="state-value turn-holder">
                  {agentState.turn_holder || '없음'}
                </span>
              </div>
              
              <div className="state-item">
                <span className="state-label">현재 송출 텍스트</span>
                <span className="state-value broadcast-text">
                  {agentState.broadcast_text || '(없음)'}
                </span>
              </div>
              
              {agentState.stenographers?.length > 0 && (
                <div className="state-item">
                  <span className="state-label">속기사 텍스트</span>
                  <div className="stenographer-texts">
                    {agentState.stenographers.map((s) => (
                      <div key={s.identity} className="steno-text-item">
                        <span className="steno-identity">
                          {s.identity.slice(0, 10)}
                          {s.identity === agentState.turn_holder && ' ⭐'}
                        </span>
                        <span className="steno-text">{s.text || '(입력 없음)'}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              
              {agentState.updated_at && (
                <div className="state-meta">
                  마지막 업데이트: {new Date(agentState.updated_at).toLocaleTimeString('ko-KR')}
                </div>
              )}
            </div>
          ) : (
            <div className="agent-status-notice">
              ⚠️ RoomAgent 상태를 조회할 수 없습니다.
              <br />
              Redis 연결을 확인하세요.
            </div>
          )}
        </div>
        
        {broadcastHistory.length > 0 && (
          <div className="detail-section">
            <h3>송출 이력 (최근 20건)</h3>
            <div className="broadcast-history">
              {broadcastHistory.map((item, idx) => (
                <div key={idx} className="history-item">
                  <div className="history-header">
                    <span className="history-sender">{item.sender?.slice(0, 10)}</span>
                    <span className="history-time">
                      {new Date(item.timestamp).toLocaleTimeString('ko-KR')}
                    </span>
                  </div>
                  <div className="history-text">{item.text}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default RoomDetail
