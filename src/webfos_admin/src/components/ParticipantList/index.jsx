import './styles.css'

function ParticipantList({ participants }) {
  const getRole = (participant) => {
    if (participant.identity?.startsWith('ingress-')) return 'ingress'
    if (participant.identity?.startsWith('agent-')) return 'agent'
    if (participant.role) return participant.role
    return 'stenographer'
  }
  
  const getRoleLabel = (role) => {
    switch (role) {
      case 'ingress': return 'Ingress'
      case 'agent': return 'Agent'
      case 'stenographer': return '속기사'
      case 'reviewer': return '검수자'
      default: return role
    }
  }
  
  const getRoleClass = (role) => {
    switch (role) {
      case 'ingress': return 'role-ingress'
      case 'agent': return 'role-agent'
      case 'stenographer': return 'role-stenographer'
      case 'reviewer': return 'role-reviewer'
      default: return ''
    }
  }
  
  return (
    <div className="participant-list">
      {participants.map((p, idx) => {
        const role = getRole(p)
        return (
          <div key={p.identity || idx} className="participant-item">
            <div className="participant-info">
              <span className="participant-identity">
                {p.identity?.slice(0, 16) || `참가자 ${idx + 1}`}
              </span>
              <span className={`participant-role ${getRoleClass(role)}`}>
                {getRoleLabel(role)}
              </span>
            </div>
            <div className="participant-meta">
              {p.joined_at && (
                <span>입장: {new Date(p.joined_at).toLocaleTimeString('ko-KR')}</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

export default ParticipantList
