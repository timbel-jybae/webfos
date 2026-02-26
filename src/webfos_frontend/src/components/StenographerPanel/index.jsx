/**
 * 속기사 텍스트 패널 컴포넌트
 * 
 * [advice from AI] 턴 관리 기능:
 * - identity: 참가자 UUID
 * - text: 표시할 텍스트 (App에서 관리)
 * - isMyPanel: 본인 패널 여부 (편집 가능)
 * - hasTurn: 송출 권한 보유 여부
 * - onTextChange: 텍스트 변경 콜백
 * - onBroadcast: 송출 버튼 클릭 콜백
 */

import './styles.css'

export function StenographerPanel({ 
  identity = '',
  index = 1, 
  text = '', 
  isMyPanel = false,
  hasTurn = false,
  onTextChange,
  onBroadcast,
}) {
  // [advice from AI] 로컬 상태 제거, App에서 텍스트 상태 관리
  
  const handleChange = (e) => {
    if (!isMyPanel) return
    onTextChange?.(e.target.value)
  }
  
  const handleBroadcast = () => {
    if (hasTurn && isMyPanel && text.trim()) {
      onBroadcast?.(text)
    }
  }
  
  // [advice from AI] identity 앞 8자리만 표시
  const displayIdentity = identity?.slice(0, 8) || `속기사_${index}`
  
  return (
    <div className={`stenographer-panel ${hasTurn ? 'has-turn' : ''} ${isMyPanel ? 'my-panel' : ''}`}>
      <div className="panel-header">
        <span className="keyboard-icon">⌨️</span>
        <span className="panel-identity">{displayIdentity}</span>
        {hasTurn && <span className="turn-badge">✓ 송출 권한</span>}
        {isMyPanel && <span className="my-badge">나</span>}
      </div>
      <div className="panel-content">
        <textarea
          className="steno-input"
          value={text}
          onChange={handleChange}
          placeholder={isMyPanel ? '텍스트를 입력하세요...' : ''}
          readOnly={!isMyPanel}
        />
        {isMyPanel && hasTurn && (
          <button 
            className="broadcast-btn"
            onClick={handleBroadcast}
            disabled={!text.trim()}
          >
            송출
          </button>
        )}
      </div>
    </div>
  )
}

export default StenographerPanel
