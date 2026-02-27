import { useState, useCallback } from 'react'
import * as adminApi from '../services/adminApi'

export function useAdminApi() {
  const [rooms, setRooms] = useState([])
  const [roomDetail, setRoomDetail] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  
  const fetchRooms = useCallback(async () => {
    setLoading(true)
    setError(null)
    
    try {
      const data = await adminApi.fetchRooms()
      setRooms(data.rooms || [])
    } catch (err) {
      console.error('[useAdminApi] fetchRooms 오류:', err)
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])
  
  const fetchRoomDetail = useCallback(async (roomName) => {
    try {
      const data = await adminApi.fetchRoomDetail(roomName)
      setRoomDetail(data)
    } catch (err) {
      console.error('[useAdminApi] fetchRoomDetail 오류:', err)
      setRoomDetail(null)
    }
  }, [])
  
  return {
    rooms,
    roomDetail,
    loading,
    error,
    fetchRooms,
    fetchRoomDetail,
  }
}
