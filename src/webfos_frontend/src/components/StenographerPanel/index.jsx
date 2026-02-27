/**
 * 속기사 텍스트 패널 컴포넌트
 * 
 * [advice from AI] 턴 관리 및 STT 편집 모드 기능:
 * - identity: 참가자 UUID
 * - text: 표시할 텍스트 (App에서 관리)
 * - isMyPanel: 본인 패널 여부 (편집 가능)
 * - hasTurn: 송출 권한 보유 여부
 * - editMode: 편집 모드 여부 (STT 갱신 일시 중지)
 * - onTextChange: 텍스트 변경 콜백
 * - onBroadcast: 송출 버튼 클릭 콜백
 * - onEditStart: 편집 모드 시작 콜백 (포커스 시)
 * - onEditEnd: 편집 모드 종료 콜백 (F2 키 입력 시)
 */

import './styles.css'

export function StenographerPanel({ 
  identity = '',
  index = 1, 
  text = '', 
  isMyPanel = false,
  hasTurn = false,
  editMode = false,
  onTextChange,
  onBroadcast,
  onEditStart,
  onEditEnd,
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
  
  // [advice from AI] 포커스 이벤트 → 편집 모드 시작
  const handleFocus = () => {
    if (!isMyPanel) return
    onEditStart?.()
  }
  
  // [advice from AI] 키 이벤트 처리
  // - F2: 편집 모드 종료
  // - 일반 키 입력: 편집 모드가 아니면 편집 모드 시작 (포커스 유지 상태에서 재진입 지원)
  const handleKeyDown = (e) => {
    if (!isMyPanel) return
    
    if (e.key === 'F2') {
      e.preventDefault()
      onEditEnd?.(text)
      return
    }
    
    // [advice from AI] 편집 모드가 아니고, 실제 문자 입력 키인 경우 편집 모드 시작
    // (Ctrl, Alt, Shift 단독 키나 특수 키는 제외)
    if (!editMode && !e.ctrlKey && !e.altKey && !e.metaKey && e.key.length === 1) {
      onEditStart?.()
    }
  }
  
  // [advice from AI] identity 앞 8자리만 표시
  const displayIdentity = identity?.slice(0, 8) || `속기사_${index}`
  
  return (
    <div className={`stenographer-panel ${hasTurn ? 'has-turn' : ''} ${isMyPanel ? 'my-panel' : ''} ${editMode ? 'edit-mode' : ''}`}>
      <div className="panel-header">
        <span className="keyboard-icon">⌨️</span>
        <span className="panel-identity">{displayIdentity}</span>
        {hasTurn && <span className="turn-badge">✓ 송출 권한</span>}
        {isMyPanel && <span className="my-badge">나</span>}
        {isMyPanel && editMode && <span className="edit-badge">✏️ 편집 중 (F2: 완료)</span>}
      </div>
      <div className="panel-content">
        <textarea
          className="steno-input"
          value={text}
          onChange={handleChange}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          placeholder={isMyPanel ? '텍스트를 입력하세요... (F2: 편집 완료)' : ''}
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
