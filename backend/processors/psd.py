"""
PSD 功率谱密度分析
"""
import numpy as np
from scipy import signal as sig


def compute_psd(data, fs=500, nperseg=1024, freq_max=50):
    """计算单通道PSD
    data: 1D array (n_samples,)
    returns: freqs, psd
    """
    nperseg_actual = min(nperseg, len(data)); noverlap = max(1, nperseg_actual // 2) if nperseg_actual > 2 else 0
    freqs, psd = sig.welch(data, fs=fs, nperseg=nperseg_actual, noverlap=noverlap)
    mask = freqs <= freq_max
    return freqs[mask], psd[mask]


def compute_psd_multi(raw, fs=500, nperseg=1024, freq_max=50):
    """多通道PSD
    raw: (n_channels, n_samples)
    returns: dict {ch_name: {"freqs": [...], "psd": [...]}}
    """
    result = {}
    for ch in range(raw.shape[0]):
        freqs, psd = compute_psd(raw[ch], fs=fs, nperseg=nperseg, freq_max=freq_max)
        result[f"Ch{ch}"] = {"freqs": freqs.tolist(), "psd": psd.tolist()}
    return result


# 标准频段定义 (IEEE/ISCEV)
BANDS = {
    "delta": (1, 4),
    "theta": (4, 8),
    "alpha": (8, 13),
    "beta":  (13, 30),
    "gamma": (30, 50),
}

# 成人正常参考范围 (绝对功率 µV², 各频段中位数±1SD)
# 来源: aggregate from multiple normative studies
REF_RANGES = {
    "delta": {"low": 5, "mid": 25, "high": 80},
    "theta": {"low": 3, "mid": 15, "high": 50},
    "alpha": {"low": 5, "mid": 30, "high": 120},
    "beta":  {"low": 2, "mid": 10, "high": 40},
    "gamma": {"low": 0.5, "mid": 3, "high": 15},
}


def band_power_from_psd(freqs, psd, bands=None):
    """从PSD计算各频段绝对功率(µV²)
    returns: {band_name: absolute_power}
    """
    if bands is None:
        bands = BANDS
    result = {}
    for name, (lo, hi) in bands.items():
        mask = (freqs >= lo) & (freqs < hi)
        if np.any(mask):
            # 功率谱密度积分 (梯形法)
            result[name] = float(np.trapezoid(psd[mask], freqs[mask]))
        else:
            result[name] = 0.0
    return result


def band_statistics(freqs, psd, bands=None, ref_ranges=None):
    """计算频段统计：绝对功率、相对功率、参考范围对比
    returns: {band: {abs, rel, status}}
    """
    if bands is None:
        bands = BANDS
    if ref_ranges is None:
        ref_ranges = REF_RANGES

    abs_powers = band_power_from_psd(freqs, psd, bands)
    total = sum(abs_powers.values()) or 1.0

    result = {}
    for name, power in abs_powers.items():
        ref = ref_ranges.get(name, {})
        mid = ref.get("mid", 0)
        if mid > 0:
            ratio = power / mid
            if ratio < 0.5:
                status = "偏低"
            elif ratio > 2.0:
                status = "偏高"
            else:
                status = "正常"
        else:
            status = "-"
        result[name] = {
            "abs": round(power, 2),
            "rel": round(power / total * 100, 1),
            "status": status,
        }
    return result


def compute_stats_multi(raw, fs=500, nperseg=1024, freq_max=50):
    """多通道频段统计
    raw: (n_channels, n_samples)
    returns: {ch_name: {band: {abs, rel, status}}}
    """
    result = {}
    for ch in range(raw.shape[0]):
        freqs, psd = compute_psd(raw[ch], fs=fs, nperseg=min(nperseg, len(raw[ch])), freq_max=freq_max)
        result[f"Ch{ch}"] = band_statistics(freqs, psd)
    return result
