/**
 * 지연시간 선택 드롭다운 컴포넌트
 * 
 * [advice from AI] 검수자용 영상 지연시간 선택
 */

import { DELAY_OPTIONS } from '../../utils/constants'
import './styles.css'

export function DelaySelector({ value, onChange, disabled = false }) {
  return (
    <div className="delay-selector">
      <label htmlFor="delay-select">지연 선택:</label>
      <select
        id="delay-select"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        disabled={disabled}
      >
        {DELAY_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    </div>
  )
}

export default DelaySelector
