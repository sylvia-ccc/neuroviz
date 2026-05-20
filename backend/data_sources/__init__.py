"""
数据源基类和空文件
"""

class BaseDataSource:
    """数据源基类"""
    
    def __init__(self, n_channels: int = 2, fs: int = 500):
        self.n_channels = n_channels
        self.fs = fs
        self.channel_names = [f"Ch{i}" for i in range(n_channels)]
    
    def read_frame(self, n_samples: int = 256) -> dict:
        raise NotImplementedError
    
    def close(self):
        pass
