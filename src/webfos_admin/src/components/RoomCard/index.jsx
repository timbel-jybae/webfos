import './styles.css'

function RoomCard({ room, isSelected, onClick }) {
  const participantCount = room.num_participants || 0
  const hasIngress = room.name?.startsWith('channel-')
  
  return (
    <div 
      className={`room-card ${isSelected ? 'selected' : ''}`}
      onClick={onClick}
    >
      <div className="room-card-header">
        <h3 className="room-name">{room.name}</h3>
        <span className={`room-status ${participantCount > 0 ? 'active' : 'idle'}`}>
          {participantCount > 0 ? '활성' : '대기'}
        </span>
      </div>
      
      <div className="room-card-body">
        <div className="room-info">
          <div className="info-item">
            <span className="info-label">참가자</span>
            <span className="info-value">{participantCount}명</span>
          </div>
          <div className="info-item">
            <span className="info-label">타입</span>
            <span className="info-value">{hasIngress ? 'HLS Ingress' : '일반'}</span>
          </div>
        </div>
        
        {room.created_at && (
          <div className="room-meta">
            생성: {new Date(room.created_at).toLocaleString('ko-KR')}
          </div>
        )}
      </div>
      
      <div className="room-card-footer">
        <button className="btn-detail">상세 보기</button>
      </div>
    </div>
  )
}

export default RoomCard
