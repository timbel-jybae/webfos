import './styles.css'

function Layout({ children }) {
  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <h1 className="logo">Webfos</h1>
          <span className="badge">Admin</span>
        </div>
        
        <nav className="sidebar-nav">
          <a href="#" className="nav-item active">
            <span className="nav-icon">📊</span>
            대시보드
          </a>
          <a href="#" className="nav-item disabled">
            <span className="nav-icon">👥</span>
            속기사 관리
            <span className="coming-soon">예정</span>
          </a>
          <a href="#" className="nav-item disabled">
            <span className="nav-icon">📝</span>
            송출 이력
            <span className="coming-soon">예정</span>
          </a>
          <a href="#" className="nav-item disabled">
            <span className="nav-icon">⚙️</span>
            설정
            <span className="coming-soon">예정</span>
          </a>
        </nav>
        
        <div className="sidebar-footer">
          <span className="version">v0.1.0</span>
        </div>
      </aside>
      
      <main className="main-content">
        {children}
      </main>
    </div>
  )
}

export default Layout
