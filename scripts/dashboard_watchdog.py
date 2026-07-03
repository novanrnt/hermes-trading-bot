#!/usr/bin/env python3
"""Dashboard watchdog — checks HTTP on port 5555, restarts if dead. Silent when healthy."""
import subprocess, sys, time, os, socket

HOME = r"C:\Users\Administrator\AppData\Local\hermes"
PYTHON = r"C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"

def check():
    """Return True if dashboard responds to HTTP."""
    try:
        import urllib.request
        urllib.request.urlopen("http://localhost:5555/", timeout=5)
        return True
    except Exception:
        return False

def port_in_use():
    """Return True if anything is listening on port 5555."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(("127.0.0.1", 5555))
        s.close()
        return result == 0
    except Exception:
        return False

def nuke_port():
    """Kill EVERY process holding port 5555. Aggressive, but necessary on Windows to avoid zombie stacking."""
    try:
        # Method 1: kill by port via netstat
        result = subprocess.run(
            'netstat -ano | findstr ":5555"',
            capture_output=True, text=True, timeout=5, shell=True
        )
        killed = set()
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and parts[-1].isdigit():
                pid = parts[-1]
                if pid not in killed:
                    subprocess.run(
                        ["cmd.exe", "/c", f"taskkill /F /PID {pid}"],
                        capture_output=True, timeout=5
                    )
                    killed.add(pid)
        time.sleep(2)
    except Exception:
        pass

def restart():
    """Clear cache and start ONE clean dashboard instance."""
    import glob as g
    for cache in g.glob(f"{HOME}/dashboard/__pycache__/server*"):
        os.remove(cache)
    for cache in g.glob(f"{HOME}/__pycache__/health_check*"):
        os.remove(cache)
    
    subprocess.Popen(
        [PYTHON, "-B", f"{HOME}/dashboard/server.py"],
        cwd=f"{HOME}/dashboard",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

if __name__ == "__main__":
    if check():
        sys.exit(0)  # Healthy — silent
    
    # Dead — nuke everything on port, then restart clean
    nuke_port()
    time.sleep(1)
    
    # Verify port is truly clear
    for i in range(5):
        if not port_in_use():
            break
        nuke_port()
        time.sleep(2)
    
    if port_in_use():
        print("⚠️ Dashboard restart failed — port 5555 still in use")
        sys.exit(1)
    
    restart()
    time.sleep(5)
    
    if check():
        print("🔄 Dashboard auto-restarted — back online")
    else:
        print("⚠️ Dashboard restart failed — manual check needed")
