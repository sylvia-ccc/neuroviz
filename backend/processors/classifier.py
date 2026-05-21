"""
在线分类器模块 — BCI实时解码
支持MI/P300/SSVEP范式
"""

import numpy as np
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from collections import deque
import pickle
import os


# ===== 特征提取 =====

def extract_band_power(data: np.ndarray, fs: int, band: tuple) -> float:
    """提取单个频段功率"""
    from scipy.signal import butter, filtfilt
    
    low, high = band
    nyq = fs / 2
    
    # 确保 low < high 且都在有效范围内
    low = max(0.1, min(low / nyq, 0.99))
    high = max(low + 0.01, min(high / nyq, 0.99))
    
    if low >= high:
        return 0.0
    
    b, a = butter(4, [low, high], btype='band')
    filtered = filtfilt(b, a, data, axis=-1)
    power = np.mean(filtered ** 2)
    return power


def extract_features_mi(epoch: np.ndarray, fs: int) -> np.ndarray:
    """
    运动想象(MI)特征提取
    输入: (n_channels, n_samples)
    输出: 特征向量
    """
    # 频段定义
    bands = {
        'mu': (8, 13),      # μ节律
        'beta': (13, 30),   # β节律
        'gamma': (30, 45)   # γ节律
    }
    
    features = []
    
    # 各频段功率
    for band_name, band_range in bands.items():
        for ch in range(epoch.shape[0]):
            power = extract_band_power(epoch[ch:ch+1], fs, band_range)
            features.append(np.log(power + 1e-10))  # 对数功率
    
    # ERD/ERS指数 (Event-Related Desynchronization/Synchronization)
    # 需要基线数据，这里简化为频段比值
    if epoch.shape[0] >= 2:
        mu_c3 = extract_band_power(epoch[0:1], fs, (8, 13))
        mu_c4 = extract_band_power(epoch[1:2], fs, (8, 13))
        features.append(mu_c3 / (mu_c4 + 1e-10))
    
    # 频谱熵
    from scipy.signal import welch
    for ch in range(min(3, epoch.shape[0])):
        f, psd = welch(epoch[ch], fs, nperseg=min(256, epoch.shape[1]))
        psd_norm = psd / (np.sum(psd) + 1e-10)
        entropy = -np.sum(psd_norm * np.log(psd_norm + 1e-10))
        features.append(entropy)
    
    return np.array(features)


def extract_features_p300(epoch: np.ndarray, fs: int) -> np.ndarray:
    """
    P300特征提取
    输入: (n_channels, n_samples)
    输出: 特征向量
    """
    features = []
    
    # 时域特征
    # P300峰值 (300-500ms)
    p300_start = int(0.25 * fs)
    p300_end = int(0.6 * fs)
    
    for ch in range(min(epoch.shape[0], 8)):  # 最多8通道
        if epoch.shape[1] > p300_end:
            p300_window = epoch[ch, p300_start:p300_end]
            features.extend([
                np.max(p300_window),           # 峰值
                np.argmax(p300_window) / fs,   # 峰值潜伏期
                np.mean(p300_window),          # 平均幅度
                np.std(p300_window)            # 变异性
            ])
    
    # 频域特征
    # δ/θ增强
    for band in [(1, 4), (4, 8)]:
        for ch in range(min(3, epoch.shape[0])):
            power = extract_band_power(epoch[ch:ch+1], fs, band)
            features.append(np.log(power + 1e-10))
    
    return np.array(features)


def extract_features_ssvep(epoch: np.ndarray, fs: int, 
                          target_freqs: List[float] = [10, 12, 15]) -> np.ndarray:
    """
    SSVEP特征提取
    输入: (n_channels, n_samples)
    输出: 特征向量
    """
    from scipy.signal import welch
    
    features = []
    
    # 各目标频率的PSD能量
    for ch in range(min(epoch.shape[0], 8)):
        f, psd = welch(epoch[ch], fs, nperseg=min(512, epoch.shape[1]))
        
        for target_freq in target_freqs:
            # 找目标频率附近的功率
            idx = np.argmin(np.abs(f - target_freq))
            power = np.mean(psd[max(0, idx-2):idx+3])
            features.append(np.log(power + 1e-10))
    
    # CCA特征 (简化版)
    # 检测最强SSVEP频率
    max_power_freq = 0
    max_power = 0
    for target_freq in target_freqs:
        for ch in range(min(epoch.shape[0], 4)):
            power = extract_band_power(epoch[ch:ch+1], fs, 
                                      (target_freq - 0.5, target_freq + 0.5))
            if power > max_power:
                max_power = power
                max_power_freq = target_freq
    
    features.append(max_power_freq)
    
    return np.array(features)


# ===== 分类器 =====

class OnlineClassifier:
    """在线分类器基类"""
    
    def __init__(self, paradigm: str = 'mi'):
        self.paradigm = paradigm
        self.model = None
        self.is_trained = False
        self.classes = []
        self.feature_buffer = deque(maxlen=100)
        self.label_buffer = deque(maxlen=100)
        
    def extract_features(self, epoch: np.ndarray, fs: int) -> np.ndarray:
        """根据范式提取特征"""
        if self.paradigm == 'mi':
            return extract_features_mi(epoch, fs)
        elif self.paradigm == 'p300':
            return extract_features_p300(epoch, fs)
        elif self.paradigm == 'ssvep':
            return extract_features_ssvep(epoch, fs)
        else:
            raise ValueError(f"Unknown paradigm: {self.paradigm}")
    
    def train(self, X: np.ndarray, y: np.ndarray):
        """训练分类器"""
        from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
        from sklearn.preprocessing import StandardScaler
        
        # 标准化
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # LDA分类器
        self.model = LinearDiscriminantAnalysis()
        self.model.fit(X_scaled, y)
        
        self.classes = list(self.model.classes_)
        self.is_trained = True
        
        print(f"[Classifier] Trained on {len(X)} samples, classes: {self.classes}")
    
    def predict(self, epoch: np.ndarray, fs: int) -> Tuple[str, float]:
        """
        预测
        返回: (预测类别, 置信度)
        """
        if not self.is_trained:
            return "unknown", 0.0
        
        # 提取特征
        features = self.extract_features(epoch, fs)
        
        # 标准化
        features_scaled = self.scaler.transform(features.reshape(1, -1))
        
        # 预测
        pred_class = self.model.predict(features_scaled)[0]
        pred_proba = self.model.predict_proba(features_scaled)[0]
        confidence = np.max(pred_proba)
        
        return str(pred_class), float(confidence)
    
    def update(self, epoch: np.ndarray, fs: int, label: str):
        """在线更新（增量训练）"""
        features = self.extract_features(epoch, fs)
        self.feature_buffer.append(features)
        self.label_buffer.append(label)
        
        # 每10个新样本重新训练
        if len(self.feature_buffer) >= 10 and len(self.feature_buffer) % 10 == 0:
            X = np.array(list(self.feature_buffer))
            y = np.array(list(self.label_buffer))
            self.train(X, y)
    
    def save(self, path: str):
        """保存模型"""
        data = {
            'model': self.model,
            'scaler': self.scaler,
            'classes': self.classes,
            'paradigm': self.paradigm
        }
        with open(path, 'wb') as f:
            pickle.dump(data, f)
        print(f"[Classifier] Saved to {path}")
    
    def load(self, path: str):
        """加载模型"""
        with open(path, 'rb') as f:
            data = pickle.load(f)
        self.model = data['model']
        self.scaler = data['scaler']
        self.classes = data['classes']
        self.paradigm = data['paradigm']
        self.is_trained = True
        print(f"[Classifier] Loaded from {path}")


# ===== BCI Session Manager =====

@dataclass
class BCISession:
    """BCI会话状态"""
    paradigm: str = 'mi'
    trial_count: int = 0
    correct_count: int = 0
    predictions: List[dict] = field(default_factory=list)
    
    def accuracy(self) -> float:
        if self.trial_count == 0:
            return 0.0
        return self.correct_count / self.trial_count


class BCIManager:
    """BCI管理器 — 集成分类器、Marker、实时推理"""
    
    def __init__(self, paradigm: str = 'mi', model_path: Optional[str] = None):
        self.paradigm = paradigm
        self.classifier = OnlineClassifier(paradigm=paradigm)
        self.session = BCISession(paradigm=paradigm)
        
        # 加载预训练模型
        if model_path and os.path.exists(model_path):
            self.classifier.load(model_path)
        
        # 实时数据缓冲
        self.epochs_buffer = deque(maxlen=1000)
        
    def process_epoch(self, epoch: np.ndarray, fs: int, 
                     marker_name: str = None) -> Optional[dict]:
        """
        处理单个epoch
        返回: 预测结果字典 或 None
        """
        if not self.classifier.is_trained:
            return None
        
        # 预测
        pred_class, confidence = self.classifier.predict(epoch, fs)
        
        result = {
            'prediction': pred_class,
            'confidence': confidence,
            'marker': marker_name,
            'timestamp': time.time()
        }
        
        self.session.predictions.append(result)
        
        return result
    
    def add_training_sample(self, epoch: np.ndarray, fs: int, label: str):
        """添加训练样本"""
        self.classifier.update(epoch, fs, label)
    
    def record_trial_result(self, correct: bool):
        """记录Trial结果"""
        self.session.trial_count += 1
        if correct:
            self.session.correct_count += 1
    
    def get_accuracy(self) -> float:
        """获取当前准确率"""
        return self.session.accuracy()
    
    def save_model(self, path: str):
        """保存模型"""
        self.classifier.save(path)
    
    def reset_session(self):
        """重置会话"""
        self.session = BCISession(paradigm=self.paradigm)


import time  # 确保time已导入
