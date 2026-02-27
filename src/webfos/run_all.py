"""
[advice from AI] 로컬 개발용 통합 실행 스크립트

Worker와 API 서버를 순차적으로 실행합니다.
Ctrl+C로 종료 시 Worker도 함께 종료됩니다.

사용법:
    python run_all.py
    python run_all.py --worker-only   # Worker만 실행
    python run_all.py --api-only      # API만 실행
"""

import subprocess
import sys
import time
import signal
import os

worker_process = None


def cleanup(sig, frame):
    """종료 시 Worker 프로세스 정리"""
    print("\n[run_all] 종료 중...")
    if worker_process and worker_process.poll() is None:
        worker_process.terminate()
        try:
            worker_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            worker_process.kill()
        print("[run_all] Worker 종료됨")
    sys.exit(0)


def main():
    global worker_process
    
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)
    
    worker_only = "--worker-only" in sys.argv
    api_only = "--api-only" in sys.argv
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    print("[run_all] 작업 디렉토리:", os.getcwd())
    
    if not api_only:
        print("[run_all] Worker 시작...")
        worker_process = subprocess.Popen(
            [sys.executable, "-m", "agents.room_agent_worker", "dev"],
            cwd=script_dir,
        )
        time.sleep(2)
        
        if worker_process.poll() is not None:
            print("[run_all] Worker 시작 실패!")
            sys.exit(1)
        
        print(f"[run_all] Worker 실행 중 (PID: {worker_process.pid})")
    
    if worker_only:
        print("[run_all] Worker만 실행 (Ctrl+C로 종료)")
        try:
            worker_process.wait()
        except KeyboardInterrupt:
            cleanup(None, None)
        return
    
    print("[run_all] API 서버 시작...")
    try:
        subprocess.run(
            [sys.executable, "main.py"],
            cwd=script_dir,
        )
    except KeyboardInterrupt:
        pass
    finally:
        cleanup(None, None)


if __name__ == "__main__":
    main()
