/**
 * LiveKit Room 연결 관리 훅
 * 
 * - connect(wsUrl, token): 룸 연결
 * - disconnect(): 연결 해제
 * - room: Room 인스턴스
 * - connectionState: 연결 상태
 * - participants: 참가자 목록
 * - videoTrack, audioTrack: 구독된 트랙
 * 
 * [advice from AI] 클라이언트 측 버퍼링 사용:
 * - 검수자도 실시간 트랙(ingress-hls-source)을 구독
 * - 클라이언트 측에서 useDelayBuffer로 지연 재생
 */

import { useState, useRef, useCallback, useEffect } from 'react'
import { Room, RoomEvent, Track, ConnectionState, VideoQuality } from 'livekit-client'
import { REALTIME_IDENTITY, CONNECTION_STATE } from '../utils/constants'

export function useLiveKit({ isReviewer = false } = {}) {
  const [connectionState, setConnectionState] = useState(CONNECTION_STATE.DISCONNECTED)
  const [participants, setParticipants] = useState([])
  const [videoTrack, setVideoTrack] = useState(null)
  const [audioTrack, setAudioTrack] = useState(null)
  const [error, setError] = useState(null)
  // [advice from AI] 로컬 참가자 identity 상태 추가
  const [localIdentity, setLocalIdentity] = useState(null)
  
  const roomRef = useRef(null)
  const connectingRef = useRef(false)
  // [advice from AI] DataChannel 메시지 콜백 저장
  const dataCallbacksRef = useRef([])
  
  const updateParticipants = useCallback(() => {
    if (!roomRef.current) return
    const remotes = Array.from(roomRef.current.remoteParticipants.values())
    setParticipants(remotes.map(p => ({
      identity: p.identity,
      name: p.name,
      isSpeaking: p.isSpeaking,
    })))
  }, [])
  
  // [advice from AI] isReviewer를 인자로 직접 받아 setState 비동기 문제 해결
  const connect = useCallback(async (wsUrl, token, isReviewerArg = false) => {
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
    
    // [advice from AI] 인자로 받은 isReviewerArg 사용 (setState 비동기 문제 해결)
    const reviewerMode = isReviewerArg
    console.log('[LiveKit] connect 시작, isReviewer:', reviewerMode)
    
    try {
      // [advice from AI] 검수자는 고해상도 필요, adaptiveStream 비활성화
      const room = new Room({
        adaptiveStream: reviewerMode ? false : true,  // 검수자는 항상 최고 해상도
        dynacast: true,
        // [advice from AI] 검수자는 클라이언트 측 버퍼링 사용하므로 오디오 자동 재생 비활성화
        webAudioMix: !reviewerMode,
      })
      console.log('[LiveKit] Room 생성, adaptiveStream:', reviewerMode ? 'disabled' : 'enabled')
      
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
        
        // [advice from AI] 클라이언트 측 버퍼링 사용
        // 검수자/참가자 모두 실시간 트랙(ingress-hls-source)만 수신
        // 검수자는 클라이언트에서 useDelayBuffer로 지연 재생
        if (participant.identity !== REALTIME_IDENTITY) {
          console.log(`[LiveKit] ${participant.identity} 트랙 구독 해제 (대상: ${REALTIME_IDENTITY})`)
          publication.setSubscribed(false)
          return
        }
        
        if (track.kind === Track.Kind.Video) {
          console.log('[LiveKit] 비디오 트랙 설정:', participant.identity, 'reviewerMode:', reviewerMode)
          // [advice from AI] 검수자는 최고 품질로 설정
          if (reviewerMode) {
            console.log('[LiveKit] 검수자 품질 설정 시도, setVideoQuality 존재:', !!publication.setVideoQuality)
            if (publication.setVideoQuality) {
              publication.setVideoQuality(VideoQuality.HIGH)
              console.log('[LiveKit] 비디오 품질 HIGH로 설정 완료')
            }
          }
          setVideoTrack(track)
        } else if (track.kind === Track.Kind.Audio) {
          console.log('[LiveKit] 오디오 트랙 설정:', participant.identity)
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
        setLocalIdentity(null)
      })
      
      // [advice from AI] DataChannel 메시지 수신 핸들러
      room.on(RoomEvent.DataReceived, (payload, participant) => {
        try {
          const decoder = new TextDecoder()
          const jsonStr = decoder.decode(payload)
          const message = JSON.parse(jsonStr)
          console.log('[LiveKit] DataChannel 수신:', message, 'from:', participant?.identity)
          
          // 등록된 콜백 호출
          dataCallbacksRef.current.forEach(cb => {
            try {
              cb(message, participant?.identity)
            } catch (e) {
              console.error('[LiveKit] DataChannel 콜백 오류:', e)
            }
          })
        } catch (e) {
          console.error('[LiveKit] DataChannel 파싱 오류:', e)
        }
      })
      
      // 연결
      await room.connect(wsUrl, token)
      connectingRef.current = false
      
      // [advice from AI] 연결 후 localParticipant identity 저장
      const myIdentity = room.localParticipant?.identity
      setLocalIdentity(myIdentity)
      console.log('[LiveKit] 내 identity:', myIdentity)
      
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
      
      // [advice from AI] 실시간 트랙만 구독 (검수자/참가자 모두)
      room.remoteParticipants.forEach((p) => {
        if (p.identity !== REALTIME_IDENTITY) {
          console.log(`[LiveKit] 연결 후 ${p.identity} 트랙 구독 해제 (대상: ${REALTIME_IDENTITY})`)
          p.trackPublications.forEach((pub) => pub.setSubscribed(false))
        }
      })
      
      updateParticipants()
      
    } catch (err) {
      console.error('[LiveKit] 연결 실패:', err)
      connectingRef.current = false
      setError(err.message)
      setConnectionState(CONNECTION_STATE.DISCONNECTED)
      throw err
    }
  }, [updateParticipants])
  
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
    setLocalIdentity(null)
  }, [])
  
  // [advice from AI] DataChannel 메시지 전송
  const sendData = useCallback(async (message, destinationIdentities = null) => {
    if (!roomRef.current?.localParticipant) {
      console.warn('[LiveKit] sendData: 연결되지 않음')
      return false
    }
    
    try {
      const encoder = new TextEncoder()
      const data = encoder.encode(JSON.stringify(message))
      
      const options = destinationIdentities 
        ? { destinationIdentities }
        : undefined
      
      await roomRef.current.localParticipant.publishData(data, options)
      console.log('[LiveKit] DataChannel 전송:', message)
      return true
    } catch (e) {
      console.error('[LiveKit] DataChannel 전송 오류:', e)
      return false
    }
  }, [])
  
  // [advice from AI] DataChannel 메시지 수신 콜백 등록
  const onDataReceived = useCallback((callback) => {
    dataCallbacksRef.current.push(callback)
    
    // cleanup 함수 반환
    return () => {
      const idx = dataCallbacksRef.current.indexOf(callback)
      if (idx !== -1) {
        dataCallbacksRef.current.splice(idx, 1)
      }
    }
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
    // [advice from AI] 턴 관리용 추가 반환값
    localIdentity,
    sendData,
    onDataReceived,
  }
}

export default useLiveKit
