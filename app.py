import subprocess
import signal
import os
import atexit
import threading
import time
from flask import Flask, request, jsonify

app = Flask(__name__)

# 存儲正在運行的端口轉發進程 { local_port: process }
forwarding_processes = {}

SSH_USER = "root"  # 替換為你的 SSH 用戶
SSH_HOST = "8.219.139.154"  # 替換為你的雲服務器
SSH_PORT = 22  # SSH 端口，默認 22
SSH_KEY_PATH = "C:\\Users\\WINDOWS 11\\.ssh\\id_rsa"  # SSH 私鑰路徑

def print_forwarding_status():
    """每10秒打印當前端口轉發狀態"""
    while True:
        if forwarding_processes:
            print("\nCurrent port forwarding status:")
            for port, process in forwarding_processes.items():
                if process.poll() is None:  # 檢查進程是否還在運行
                    print(f"Local port {port} is being forwarded (PID: {process.pid})")
                else:
                    print(f"Local port {port} forwarding has stopped")
        else:
            print("\nNo active port forwarding")
        time.sleep(10)

# 啟動狀態打印線程
status_thread = threading.Thread(target=print_forwarding_status, daemon=True)
status_thread.start()

def cleanup_forwarding():
    """清理所有轉發進程"""
    for port, process in forwarding_processes.items():
        try:
            os.kill(process.pid, signal.SIGTERM)
            print(f"Stopped forwarding for port {port}")
        except:
            pass
    forwarding_processes.clear()

# 註冊退出時的清理函數
atexit.register(cleanup_forwarding)

def setup_port_forwarding(local_port, remote_port):
    """設置端口轉發"""
    # ssh 命令
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",  # 忽略主機密鑰檢查
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=3",
        "-i", SSH_KEY_PATH,
        "-N",
        "-R", f"{remote_port}:127.0.0.1:{local_port}",
        f"{SSH_USER}@{SSH_HOST}"
    ]

    print(" ".join(cmd))

    # 啟動進程
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    # 等待一段時間檢查進程是否正常運行
    try:
        stdout, stderr = process.communicate(timeout=5)
        if process.returncode != 0:
            error_msg = stderr.decode('utf-8')
            print(f"Failed to start forwarding: {error_msg}")
            return None
    except subprocess.TimeoutExpired:
        # 如果進程沒有退出,說明正在運行中
        forwarding_processes[local_port] = process
        print(f"Successfully started forwarding local port {local_port} to {SSH_HOST}:{remote_port}")
        return process
    except Exception as e:
        process.kill()
        print(f"Failed to start forwarding: {str(e)}")
        return None

@app.route('/start_forwarding', methods=['POST'])
def start_forwarding():
    data = request.json
    local_port = data.get("local_port")

    if not local_port:
        return jsonify({"error": "Missing local_port"}), 400

    if local_port in forwarding_processes:
        return jsonify({"error": f"Port {local_port} is already forwarded"}), 400

    # 從服務器獲取可用端口
    try:
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=no",
            "-i", SSH_KEY_PATH,
            f"{SSH_USER}@{SSH_HOST}",
            "python3 -c 'import socket; s=socket.socket(); s.bind((\"0.0.0.0\", 0)); print(s.getsockname()[1]); s.close()'"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            return jsonify({"error": "Failed to get available remote port"}), 500
        
        remote_port = int(result.stdout.strip())
    except Exception as e:
        return jsonify({"error": f"Failed to get available remote port: {str(e)}"}), 500

    process = setup_port_forwarding(local_port, remote_port)
    if not process:
        return jsonify({"error": "Failed to start forwarding"}), 500

    return jsonify({
        "message": f"Forwarding local port {local_port} to {SSH_HOST}:{remote_port}",
        "pid": process.pid,
        "remote_port": remote_port
    })

@app.route('/stop_forwarding', methods=['POST'])
def stop_forwarding():
    data = request.json
    local_port = data.get("local_port")

    if not local_port:
        return jsonify({"error": "Missing local_port"}), 400

    process = forwarding_processes.pop(local_port, None)
    if not process:
        return jsonify({"error": f"No forwarding found for port {local_port}"}), 404

    os.kill(process.pid, signal.SIGTERM)  # 終止進程
    return jsonify({"message": f"Stopped forwarding for port {local_port}"})

@app.route('/get_forwarding_status', methods=['GET'])
def get_forwarding_status():
    return jsonify({"forwarding_processes": {port: process.pid for port, process in forwarding_processes.items()}})

@app.route("/health", methods=['GET'])
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    # 啓動時自動設置端口轉發
    setup_port_forwarding(40000, 4123)
    setup_port_forwarding(5000, 5123)
    app.run(host="0.0.0.0", port=5000)
