/**
 * 화질 선택 드롭다운 컴포넌트
 */

import { QUALITY_OPTIONS } from '../../utils/constants'
import './styles.css'

export function QualitySelector({ value, onChange, disabled = false }) {
  return (
    <div className="quality-selector">
      <label htmlFor="quality-select">화질 선택:</label>
      <select
        id="quality-select"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        {Object.entries(QUALITY_OPTIONS).map(([key, opt]) => (
          <option key={key} value={key}>{opt.label}</option>
        ))}
      </select>
    </div>
  )
}

export default QualitySelector
