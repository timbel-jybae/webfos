import { useState, useEffect, useCallback } from 'react'
import Layout from './components/Layout'
import RoomCard from './components/RoomCard'
import RoomDetail from './components/RoomDetail'
import { useAdminApi } from './hooks/useAdminApi'
import './App.css'

function App() {
  const { rooms, loading, error, fetchRooms, fetchRoomDetail, roomDetail } = useAdminApi()
  const [selectedRoom, setSelectedRoom] = useState(null)
  
  useEffect(() => {
    fetchRooms()
    
    const interval = setInterval(() => {
      fetchRooms()
    }, 5000)
    
    return () => clearInterval(interval)
  }, [fetchRooms])
  
  const handleSelectRoom = useCallback((roomName) => {
    setSelectedRoom(roomName)
    if (roomName) {
      fetchRoomDetail(roomName)
    }
  }, [fetchRoomDetail])
  
  const handleCloseDetail = useCallback(() => {
    setSelectedRoom(null)
  }, [])
  
  const totalParticipants = rooms.reduce((sum, room) => sum + (room.num_participants || 0), 0)
  
  return (
    <Layout>
      <div className="dashboard">
        <header className="dashboard-header">
          <h1>Webfos 관리자 대시보드</h1>
          <div className="dashboard-stats">
            <div className="stat">
              <span className="stat-value">{rooms.length}</span>
              <span className="stat-label">채널</span>
            </div>
            <div className="stat">
              <span className="stat-value">{totalParticipants}</span>
              <span className="stat-label">참가자</span>
            </div>
          </div>
        </header>
        
        {error && (
          <div className="error-banner">
            {error}
          </div>
        )}
        
        <main className="dashboard-content">
          <section className="rooms-section">
            <h2>채널 목록 {loading && <span className="loading-indicator">갱신중...</span>}</h2>
            
            {rooms.length === 0 && !loading ? (
              <div className="empty-state">
                활성 채널이 없습니다.
              </div>
            ) : (
              <div className="rooms-grid">
                {rooms.map((room) => (
                  <RoomCard
                    key={room.name}
                    room={room}
                    isSelected={selectedRoom === room.name}
                    onClick={() => handleSelectRoom(room.name)}
                  />
                ))}
              </div>
            )}
          </section>
          
          {selectedRoom && (
            <RoomDetail
              roomName={selectedRoom}
              detail={roomDetail}
              onClose={handleCloseDetail}
            />
          )}
        </main>
      </div>
    </Layout>
  )
}

export default App
