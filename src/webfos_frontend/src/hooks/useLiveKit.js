/**
 * LiveKit Room 연결 관리 훅
 * 
 * - connect(wsUrl, token): 룸 연결
 * - disconnect(): 연결 해제
 * - room: Room 인스턴스
 * - connectionState: 연결 상태
 * - participants: 참가자 목록
 * - videoTrack, audioTrack: 구독된 트랙
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { Room, RoomEvent, Track, ConnectionState } from 'livekit-client'
import { REALTIME_IDENTITY, CONNECTION_STATE } from '../utils/constants'

export function useLiveKit({ isReviewer = false } = {}) {
  const [connectionState, setConnectionState] = useState(CONNECTION_STATE.DISCONNECTED)
  const [participants, setParticipants] = useState([])
  const [videoTrack, setVideoTrack] = useState(null)
  const [audioTrack, setAudioTrack] = useState(null)
  const [error, setError] = useState(null)
  
  const roomRef = useRef(null)
  const connectingRef = useRef(false)
  
  const updateParticipants = useCallback(() => {
    if (!roomRef.current) return
    const remotes = Array.from(roomRef.current.remoteParticipants.values())
    setParticipants(remotes.map(p => ({
      identity: p.identity,
      name: p.name,
      isSpeaking: p.isSpeaking,
    })))
  }, [])
  
  const connect = useCallback(async (wsUrl, token) => {
    // 이미 연결 중이거나 연결된 상태면 스킵
    if (connectingRef.current || roomRef.current?.state === 'connected') {
      console.log('[LiveKit] 이미 연결 중/연결됨, 스킵')
      return
    }
    
    // 기존 room 정리 (연결 시도 전에)
    if (roomRef.current) {
      roomRef.current.disconnect()
      roomRef.current = null
    }
    
    connectingRef.current = true
    setConnectionState(CONNECTION_STATE.CONNECTING)
    setError(null)
    
    try {
      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        // 검수자는 오디오 자동 재생 비활성화 (지연 버퍼 사용)
        webAudioMix: !isReviewer,
      })
      
      roomRef.current = room
      
      // 이벤트 핸들러 설정
      room.on(RoomEvent.ConnectionStateChanged, (state) => {
        console.log('[LiveKit] 연결 상태:', state)
        if (state === ConnectionState.Connected) {
          setConnectionState(CONNECTION_STATE.CONNECTED)
        } else if (state === ConnectionState.Disconnected) {
          setConnectionState(CONNECTION_STATE.DISCONNECTED)
        } else if (state === ConnectionState.Reconnecting) {
          setConnectionState(CONNECTION_STATE.RECONNECTING)
        }
      })
      
      room.on(RoomEvent.ParticipantConnected, (participant) => {
        console.log('[LiveKit] 참가자 입장:', participant.identity)
        updateParticipants()
      })
      
      room.on(RoomEvent.ParticipantDisconnected, (participant) => {
        console.log('[LiveKit] 참가자 퇴장:', participant.identity)
        updateParticipants()
      })
      
      room.on(RoomEvent.TrackPublished, (publication, participant) => {
        console.log('[LiveKit] 트랙 발행:', participant.identity, publication.kind, publication.source)
      })
      
      room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
        console.log('[LiveKit] 트랙 구독:', participant.identity, track.kind, {
          trackSid: track.sid,
          source: publication.source,
          muted: track.isMuted,
        })
        
        // 검수자: 실시간 소스만 수신
        if (isReviewer && participant.identity !== REALTIME_IDENTITY) {
          console.log('[LiveKit] 검수자: 실시간 외 소스 구독 해제:', participant.identity)
          publication.setSubscribed(false)
          return
        }
        
        if (track.kind === Track.Kind.Video) {
          console.log('[LiveKit] 비디오 트랙 설정')
          setVideoTrack(track)
        } else if (track.kind === Track.Kind.Audio) {
          console.log('[LiveKit] 오디오 트랙 설정')
          setAudioTrack(track)
        }
      })
      
      room.on(RoomEvent.TrackUnsubscribed, (track) => {
        if (track.kind === Track.Kind.Video) {
          setVideoTrack(null)
        } else if (track.kind === Track.Kind.Audio) {
          setAudioTrack(null)
        }
      })
      
      room.on(RoomEvent.Disconnected, () => {
        setConnectionState(CONNECTION_STATE.DISCONNECTED)
        setVideoTrack(null)
        setAudioTrack(null)
      })
      
      // 연결
      await room.connect(wsUrl, token)
      connectingRef.current = false
      
      // 연결 후 참가자 정보 로깅
      const remoteParticipants = Array.from(room.remoteParticipants.values())
      const participantInfo = remoteParticipants.map(p => ({
        identity: p.identity,
        tracks: Array.from(p.trackPublications.values()).map(t => ({
          kind: t.kind,
          source: t.source,
          subscribed: t.isSubscribed,
        }))
      }))
      console.log('[LiveKit] 연결 완료, 참가자:', participantInfo)
      
      // 검수자: 실시간 소스 외 구독 해제
      if (isReviewer) {
        room.remoteParticipants.forEach((p) => {
          if (p.identity !== REALTIME_IDENTITY) {
            p.trackPublications.forEach((pub) => pub.setSubscribed(false))
          }
        })
      }
      
      updateParticipants()
      
    } catch (err) {
      console.error('[LiveKit] 연결 실패:', err)
      connectingRef.current = false
      setError(err.message)
      setConnectionState(CONNECTION_STATE.DISCONNECTED)
      throw err
    }
  }, [isReviewer, updateParticipants])
  
  const disconnect = useCallback(async () => {
    connectingRef.current = false
    if (roomRef.current) {
      await roomRef.current.disconnect()
      roomRef.current = null
    }
    setConnectionState(CONNECTION_STATE.DISCONNECTED)
    setVideoTrack(null)
    setAudioTrack(null)
    setParticipants([])
  }, [])
  
  const startAudio = useCallback(async () => {
    if (roomRef.current) {
      await roomRef.current.startAudio()
    }
  }, [])
  
  // 컴포넌트 언마운트 시 정리 (React Strict Mode 고려)
  useEffect(() => {
    return () => {
      // 연결 중이면 정리하지 않음 (Strict Mode에서 재마운트 시 연결 유지)
      if (connectingRef.current) {
        console.log('[LiveKit] cleanup 스킵 (연결 중)')
        return
      }
      if (roomRef.current) {
        console.log('[LiveKit] cleanup: disconnect')
        roomRef.current.disconnect()
      }
    }
  }, [])
  
  return {
    room: roomRef.current,
    connectionState,
    isConnected: connectionState === CONNECTION_STATE.CONNECTED,
    participants,
    videoTrack,
    audioTrack,
    error,
    connect,
    disconnect,
    startAudio,
  }
}

export default useLiveKit
