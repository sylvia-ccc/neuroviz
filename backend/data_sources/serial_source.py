"""
串口数据源 — EEG102硬件串口读取
等待板子到货后进行协议逆向
"""

import asyncio
import serial
import serial.tools.list_ports
from typing import Optional
import numpy as np


class SerialDataSource:
    """从串口读取EEG数据，解析后推送"""

    def __init__(self, port: str = None, baudrate: int = 115200, fs_target: int = 500, n_channels: int = 2):
        self.port = port
        self.baudrate = baudrate
        self.fs_target = fs_target
        self.n_channels = n_channels
        self.channel_names = [f"CH{i+1}" for i in range(n_channels)]

        self.ser: Optional[serial.Serial] = None
        self._buffer = bytearray()
        self._scene = "relax"

        # 协议参数(等待板子到货后填充)
        self.PACKET_SIZE = 0  # 每包字节数
        self.HEADER_BYTES = b""  # 包头特征

        print(f"[SerialDataSource] 初始化: {port or '(未选择)'} @ {baudrate}bps")

    @staticmethod
    def list_ports() -> list[dict]:
        """列出所有可用串口"""
        ports = []
        for p in serial.tools.list_ports.comports():
            ports.append({
                "port": p.device,
                "name": p.name,
                "desc": p.description,
                "hwid": p.hwid,
            })
        return ports

    def connect(self, port: str = None) -> bool:
        """连接串口"""
        target_port = port or self.port
        if not target_port:
            print("[SerialDataSource] 错误: 未指定串口")
            return False

        try:
            self.ser = serial.Serial(
                port=target_port,
                baudrate=self.baudrate,
                timeout=0.1,
            )
            self.port = target_port
            print(f"[SerialDataSource] ✅ 已连接: {target_port}")
            return True
        except Exception as e:
            print(f"[SerialDataSource] ❌ 连接失败: {e}")
            return False

    def disconnect(self):
        """断开串口"""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"[SerialDataSource] 已断开: {self.port}")

    def set_scene(self, scene: str):
        self._scene = scene

    def read_frame(self, n_samples: int = 256) -> dict:
        """读取一帧数据(阻塞式, 实际使用异步)"""
        if not self.ser or not self.ser.is_open:
            return self._dummy_frame(n_samples)

        # 读取串口数据
        raw = self.ser.read(self.ser.in_waiting or 1)
        if raw:
            self._buffer.extend(raw)

        # 解析数据包(等待协议逆向)
        # TODO: 实现协议解析
        # parsed = self._parse_packets()

        # 临时: 返回模拟数据
        return self._dummy_frame(n_samples)

    async def read_frame_async(self, n_samples: int = 256) -> dict:
        """异步读取一帧(推荐用这个)"""
        # 在独立线程中读取串口(避免阻塞事件循环)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.read_frame, n_samples)

    def _dummy_frame(self, n_samples: int = 256) -> dict:
        """生成模拟数据(串口未连接时)"""
        t = np.arange(n_samples) / self.fs_target
        if self._scene == "relax":
            ch1 = 0.8 * np.sin(2 * np.pi * 10 * t) + 0.3 * np.random.randn(n_samples)
            ch2 = 0.8 * np.sin(2 * np.pi * 10 * t + 0.5) + 0.3 * np.random.randn(n_samples)
        elif self._scene == "focus":
            ch1 = 0.6 * np.sin(2 * np.pi * 20 * t) + 0.4 * np.random.randn(n_samples)
            ch2 = 0.6 * np.sin(2 * np.pi * 20 * t + 0.3) + 0.4 * np.random.randn(n_samples)
        else:  # blink
            ch1 = 0.5 * np.sin(2 * np.pi * 10 * t) + 2.0 * np.exp(-((t - 0.1) ** 2) / 0.001)
            ch2 = 0.5 * np.sin(2 * np.pi * 10 * t) + 2.0 * np.exp(-((t - 0.1) ** 2) / 0.001)

        return {
            "channels": self.channel_names,
            "raw": np.array([ch1, ch2]),
            "ch1": ch1,
            "ch2": ch2,
            "scene": self._scene,
            "t": t,
            "source": "serial_dummy",
        }

    def get_info(self) -> dict:
        return {
            "port": self.port,
            "baudrate": self.baudrate,
            "connected": self.ser is not None and self.ser.is_open,
            "n_channels": self.n_channels,
            "fs": self.fs_target,
        }
