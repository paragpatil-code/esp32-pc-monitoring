"""
Sends CPU / RAM / GPU usage + GPU temperature from Windows to an ESP32 over WiFi (UDP).

Install:   pip install psutil nvidia-ml-py
Run:       python pc_monitor_wifi.py                 (broadcasts to the LAN)
           python pc_monitor_wifi.py 192.168.1.50    (send straight to the ESP32's IP)

NVIDIA: usage and temperature come from NVML (nothing else needed).
AMD/Intel: usage comes from Windows "GPU Engine" counters. Windows has no built-in
temperature API, so run LibreHardwareMonitor (https://github.com/LibreHardwareMonitor/
LibreHardwareMonitor) in the background; this script reads GPU temp from it.
Without it, temperature shows "--" on the display.
"""
import csv
import socket
import subprocess
import sys
import threading
import time

import psutil

PORT = 4210
INTERVAL = 0.5  # seconds between updates
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

LHM_CMD = (
    "Get-CimInstance -Namespace root/LibreHardwareMonitor -ClassName Sensor | "
    "Where-Object { $_.SensorType -eq 'Temperature' -and $_.Identifier -like '*gpu*' "
    "-and $_.Name -match 'GPU Core|Hot Spot|GPU Temperature' } | "
    "Select-Object -First 1 -ExpandProperty Value"
)


class GPUReader:
    def __init__(self):
        self.usage = 0.0
        self.temp = -1
        try:
            import pynvml
            pynvml.nvmlInit()
            self._nv = pynvml
            self._handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            self.mode = "NVIDIA (NVML)"
        except Exception:
            self.mode = "Windows counters + LibreHardwareMonitor temp"
            threading.Thread(target=self._usage_loop, daemon=True).start()
            threading.Thread(target=self._temp_loop, daemon=True).start()

    def read(self):
        """Returns (usage %, temp C or -1)."""
        if self.mode.startswith("NVIDIA"):
            try:
                u = self._nv.nvmlDeviceGetUtilizationRates(self._handle).gpu
                t = self._nv.nvmlDeviceGetTemperature(
                    self._handle, self._nv.NVML_TEMPERATURE_GPU)
                return u, t
            except Exception:
                return 0, -1
        return self.usage, self.temp

    def _usage_loop(self):
        cmd = ["typeperf", r"\GPU Engine(*)\Utilization Percentage", "-si", "1"]
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                             text=True, creationflags=NO_WINDOW)
        cols_3d = None
        for row in csv.reader(p.stdout):
            if not row:
                continue
            if cols_3d is None:
                if any("GPU Engine" in c for c in row):
                    cols_3d = [i for i, c in enumerate(row) if "engtype_3D" in c]
                continue
            try:
                total = sum(float(row[i]) for i in cols_3d if i < len(row))
                self.usage = min(100.0, total)
            except ValueError:
                pass

    def _temp_loop(self):
        while True:
            try:
                out = subprocess.run(
                    ["powershell", "-NoProfile", "-Command", LHM_CMD],
                    capture_output=True, text=True, timeout=8,
                    creationflags=NO_WINDOW).stdout.strip()
                self.temp = round(float(out)) if out else -1
            except Exception:
                self.temp = -1
            time.sleep(2)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "255.255.255.255"
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    gpu = GPUReader()
    print(f"Sending to {target}:{PORT} | GPU source: {gpu.mode}")
    psutil.cpu_percent(None)  # prime the counter

    try:
        while True:
            cpu = round(psutil.cpu_percent(None))
            ram = round(psutil.virtual_memory().percent)
            usage, temp = gpu.read()
            msg = f"C:{cpu},R:{ram},G:{round(usage)},T:{temp}"
            try:
                sock.sendto(msg.encode(), (target, PORT))
            except OSError:
                pass  # network down; keep trying
            print(msg, end="   \r")
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
