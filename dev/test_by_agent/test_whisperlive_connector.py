"""
[advice from AI] WhisperLive STTConnector 단위 테스트

WhisperLive 서버 연결 및 STTConnector 클래스 테스트.
"""

import asyncio
import json
import sys
import os
import wave
import struct

# 프로젝트 루트 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src/webfos'))

from agents.stt_connector import STTConnector, STTState
from core.config import settings


async def test_server_connection():
    """서버 연결 테스트"""
    print("\n=== 1. 서버 연결 테스트 ===")
    
    connector = STTConnector()
    print(f"Host: {connector.host}, Port: {connector.port}")
    
    success = await connector.connect()
    print(f"연결 결과: {success}, 상태: {connector.state}")
    
    if success:
        await asyncio.sleep(1)
        await connector.disconnect()
        print("연결 종료 완료")
    
    return success


async def test_with_simulated_audio():
    """시뮬레이션 오디오로 테스트"""
    print("\n=== 2. 시뮬레이션 오디오 테스트 ===")
    
    results = {"partial": [], "final": []}
    
    async def on_partial(text, segments):
        print(f"  [PARTIAL] {text[:80]}...")
        results["partial"].append(text)
    
    async def on_final(text, segments):
        print(f"  [FINAL] {text}")
        results["final"].append(text)
    
    connector = STTConnector(
        on_partial=on_partial,
        on_final=on_final,
    )
    
    success = await connector.connect()
    if not success:
        print("연결 실패")
        return False
    
    print("오디오 전송 시작 (10초 무음)...")
    
    # 16kHz, mono, PCM16 무음 생성
    sample_rate = 16000
    duration_sec = 10
    
    # 1초 단위로 전송
    for i in range(duration_sec):
        # PCM16 무음 (0 값)
        silence = struct.pack('<' + 'h' * sample_rate, *([0] * sample_rate))
        await connector.send_audio(silence)
        print(f"  {i+1}초 전송 완료")
        await asyncio.sleep(0.1)
    
    print("전송 완료, 결과 대기...")
    await asyncio.sleep(3)
    
    await connector.disconnect()
    
    print(f"\n결과: partial={len(results['partial'])}, final={len(results['final'])}")
    return True


async def test_with_wav_file():
    """WAV 파일로 테스트 (파일이 있으면)"""
    print("\n=== 3. WAV 파일 테스트 ===")
    
    # 테스트 WAV 파일 경로 (없으면 스킵)
    test_wav = os.path.join(os.path.dirname(__file__), "test_audio.wav")
    if not os.path.exists(test_wav):
        print(f"테스트 파일 없음: {test_wav}")
        print("테스트 파일을 생성하려면: ")
        print("  ffmpeg -f lavfi -i 'sine=frequency=440:duration=5' -ar 16000 -ac 1 -acodec pcm_s16le test_audio.wav")
        return True  # 스킵해도 성공
    
    results = {"text": ""}
    
    async def on_partial(text, segments):
        results["text"] = text
        print(f"  [PARTIAL] {text}")
    
    async def on_final(text, segments):
        results["text"] = text
        print(f"  [FINAL] {text}")
    
    connector = STTConnector(
        on_partial=on_partial,
        on_final=on_final,
    )
    
    success = await connector.connect()
    if not success:
        print("연결 실패")
        return False
    
    # WAV 파일 읽기
    with wave.open(test_wav, 'rb') as wf:
        sample_rate = wf.getframerate()
        n_channels = wf.getnchannels()
        n_frames = wf.getnframes()
        
        print(f"WAV: {sample_rate}Hz, {n_channels}ch, {n_frames} frames")
        
        if sample_rate != 16000 or n_channels != 1:
            print("16kHz mono가 아님, 변환 필요")
            await connector.disconnect()
            return False
        
        # 청크 단위 전송 (0.5초)
        chunk_size = sample_rate // 2
        
        while True:
            audio_data = wf.readframes(chunk_size)
            if not audio_data:
                break
            
            await connector.send_audio(audio_data)
            await asyncio.sleep(0.05)
    
    print("전송 완료, 결과 대기...")
    await asyncio.sleep(3)
    
    await connector.disconnect()
    
    print(f"\n최종 결과: {results['text']}")
    return True


async def test_reconnection():
    """재연결 테스트"""
    print("\n=== 4. 재연결 테스트 ===")
    
    connector = STTConnector()
    
    # 첫 연결
    print("첫 연결...")
    success1 = await connector.connect()
    print(f"  결과: {success1}")
    
    # 종료
    await connector.disconnect()
    print("  종료 완료")
    
    await asyncio.sleep(1)
    
    # 재연결
    print("재연결...")
    success2 = await connector.connect()
    print(f"  결과: {success2}")
    
    await connector.disconnect()
    
    return success1 and success2


async def main():
    """전체 테스트 실행"""
    print("=" * 60)
    print("WhisperLive STTConnector 테스트")
    print(f"서버 URL: {settings.STT_WS_URL}")
    print(f"모델: {settings.STT_MODEL}")
    print(f"언어: {settings.STT_LANGUAGE}")
    print("=" * 60)
    
    results = []
    
    # 1. 연결 테스트
    try:
        r = await test_server_connection()
        results.append(("서버 연결", r))
    except Exception as e:
        print(f"오류: {e}")
        results.append(("서버 연결", False))
    
    # 서버 연결 실패시 중단
    if not results[0][1]:
        print("\n서버 연결 실패, 테스트 중단")
        print("WhisperLive 서버가 실행 중인지 확인하세요:")
        print("  docker-compose -f ~/Documents/Docker-composes/faster-whisper/docker-compose.yml up -d")
        return
    
    # 2. 시뮬레이션 오디오
    try:
        r = await test_with_simulated_audio()
        results.append(("시뮬레이션 오디오", r))
    except Exception as e:
        print(f"오류: {e}")
        results.append(("시뮬레이션 오디오", False))
    
    # 3. WAV 파일
    try:
        r = await test_with_wav_file()
        results.append(("WAV 파일", r))
    except Exception as e:
        print(f"오류: {e}")
        results.append(("WAV 파일", False))
    
    # 4. 재연결
    try:
        r = await test_reconnection()
        results.append(("재연결", r))
    except Exception as e:
        print(f"오류: {e}")
        results.append(("재연결", False))
    
    # 결과 요약
    print("\n" + "=" * 60)
    print("테스트 결과 요약")
    print("=" * 60)
    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  {status}: {name}")
    
    all_passed = all(r for _, r in results)
    print("\n" + ("모든 테스트 통과!" if all_passed else "일부 테스트 실패"))


if __name__ == "__main__":
    asyncio.run(main())
