/**
 * 송출 텍스트 패널 컴포넌트
 * 
 * 송출 확정된 자막을 표시한다.
 * - 속기사가 트리거하면 해당 텍스트가 여기에 표시됨
 */

import './styles.css'

export function BroadcastPanel({ text = '' }) {
  return (
    <div className="broadcast-panel">
      <div className="panel-header">
        <span className="monitor-icon">🖥️</span>
      </div>
      <div className="panel-content">
        <div className="broadcast-text">
          {text || '송출 텍스트'}
        </div>
      </div>
    </div>
  )
}

export default BroadcastPanel
