"""
2D脑地形图(Topomap)生成
用matplotlib + scipy插值生成头皮电位分布图
支持动态电极数自适应
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')  # 无GUI后端
import matplotlib.pyplot as plt
from matplotlib import cm
from scipy.interpolate import griddata
import io
import base64


# 10-20系统电极坐标 (极坐标 → 笛卡尔, 单位: 半径=1)
# 位置: Fp1/Fp2, F7/F8, F3/F4, C3/C4, P3/P4, O1/O2...
ELECTRODE_POS = {
    # 额叶 (Frontal)
    'Fp1': (-0.55, 0.65), 'Fp2': (0.55, 0.65),
    'F7': (-0.85, 0.30), 'F8': (0.85, 0.30),
    'F3': (-0.35, 0.50), 'F4': (0.35, 0.50),
    'Fz': (0.0, 0.55),
    # 中央 (Central)
    'C3': (-0.50, 0.0), 'C4': (0.50, 0.0),
    'Cz': (0.0, 0.0),
    # 顶叶 (Parietal)
    'P3': (-0.45, -0.40), 'P4': (0.45, -0.40),
    'Pz': (0.0, -0.40),
    # 枕叶 (Occipital)
    'O1': (-0.35, -0.75), 'O2': (0.35, -0.75),
    # 颞叶 (Temporal)
    'T7': (-0.95, 0.0), 'T8': (0.95, 0.0),
    # 额外(常用)
    'F1': (-0.20, 0.60), 'F2': (0.20, 0.60),
    'FC1': (-0.35, 0.25), 'FC2': (0.35, 0.25),
    'CP1': (-0.35, -0.25), 'CP2': (0.35, -0.25),
    'POz': (0.0, -0.60),
}


# 通道索引到电极名的映射（常用配置）
CHANNEL_MAPS = {
    2: ['Fp1', 'Fp2'],  # 双通道前额
    4: ['Fp1', 'Fp2', 'O1', 'O2'],  # 4通道额枕
    8: ['Fp1', 'Fp2', 'F7', 'F8', 'T7', 'T8', 'O1', 'O2'],  # 8通道常用
    14: ['Fp1', 'Fp2', 'F7', 'F8', 'F3', 'F4', 'C3', 'C4', 'P3', 'P4', 'O1', 'O2', 'Fz', 'Cz'],
    19: ['Fp1', 'Fp2', 'F7', 'F8', 'F3', 'F4', 'C3', 'C4', 'P3', 'P4', 'O1', 'O2', 'Fz', 'Cz', 'Pz', 'T7', 'T8', 'F7', 'F8'],  # 标准10-20
}


def get_electrode_names(n_channels: int, channel_names: list = None) -> list:
    """
    根据通道数返回电极名列表
    如果提供了channel_names，直接使用
    """
    if channel_names:
        return channel_names
    return CHANNEL_MAPS.get(n_channels, [f'Ch{i}' for i in range(n_channels)])


def generate_topomap(
    values: dict,  # {'Fp1': 5.2, 'Fp2': 4.8, ...}
    title: str = "EEG Topomap",
    vmin: float = None,
    vmax: float = None,
    cmap: str = 'RdBu_r',  # 红蓝(反转=暖色高激活)
    save_to: str = None,  # 文件路径(可选)
    method: str = 'auto',  # 'auto', 'nearest', 'linear', 'cubic', 'rbf'
) -> bytes:
    """
    生成2D脑地形图, 返回PNG图片bytes
    
    Args:
        values: 电极名→数值的dict
        title: 图片标题
        vmin/vmax: 颜色范围(自动计算如果为None)
        cmap: 颜色映射
        method: 插值方法('auto'自动选择)
        save_to: 保存到文件路径(可选)
    
    Returns:
        PNG图片的bytes
    """
    # 提取坐标和数值
    pos = []
    vals = []
    names = []
    for name, v in values.items():
        if name in ELECTRODE_POS:
            x, y = ELECTRODE_POS[name]
            pos.append([x, y])
            vals.append(v)
            names.append(name)
    
    if len(pos) < 2:
        raise ValueError(f"至少需要2个电极, 当前: {len(pos)}")
    
    pos = np.array(pos)
    vals = np.array(vals)
    
    # 自动计算vmin/vmax
    if vmin is None:
        vmin = vals.min()
    if vmax is None:
        vmax = vals.max()
    
    # 创建插值网格
    grid_x, grid_y = np.mgrid[-1:1:100j, -1:1:100j]
    
    # 选择插值方法
    if method == 'auto':
        n = len(pos)
        if n == 2:
            method = 'nearest'
        elif n == 3:
            method = 'linear'
        else:
            method = 'cubic'
    
    # RBF插值（更平滑）
    if method == 'rbf':
        from scipy.interpolate import RBFInterpolator
        rbf = RBFInterpolator(pos, vals, kernel='gaussian', epsilon=0.3)
        grid_points = np.column_stack([grid_x.ravel(), grid_y.ravel()])
        grid_z = rbf(grid_points).reshape(grid_x.shape)
    else:
        grid_z = griddata(pos, vals, (grid_x, grid_y), method=method, fill_value=0.0)
    if vmax is None:
        vmax = vals.max()
    
    # 绘制
    fig, ax = plt.subplots(figsize=(5, 5), dpi=100, facecolor='#0a0e14')
    ax.set_facecolor('#0a0e14')
    
    # 地形图
    im = ax.imshow(
        grid_z.T,
        extent=(-1, 1, -1, 1),
        origin='lower',
        cmap=cmap,
        vmin=vmin,
        vmax=vmax,
        alpha=0.8,
    )
    
    # 颜色条
    cbar = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.05)
    cbar.ax.tick_params(colors='#6e7681', labelsize=8)
    cbar.outline.set_edgecolor('#1e2a3a')
    
    # 电极位置和数值
    for (x, y), v, name in zip(pos, vals, names):
        ax.plot(x, y, 'o', markersize=8, color='#c9d1d9', markeredgecolor='#1e2a3a', linewidth=1.5)
        ax.text(x * 1.08, y * 1.08, f'{v:.1f}', fontsize=7, color='#c9d1d9', ha='center', va='center')
    
    # 头皮轮廓(椭圆)
    from matplotlib.patches import Ellipse
    ellipse = Ellipse((0, 0), 2.0, 2.0, edgecolor='#6e7681', facecolor='none', linewidth=1.5)
    ax.add_patch(ellipse)
    
    # 鼻子(上方三角形)
    ax.plot([0, -0.1, 0.1, 0], [1.0, 1.05, 1.05, 1.0], color='#6e7681', linewidth=1.5)
    
    # 设置
    ax.set_xlim(-1.2, 1.2)
    ax.set_ylim(-1.2, 1.2)
    ax.set_aspect('equal')
    ax.axis('off')
    fig.suptitle(title, color='#c9d1d9', fontsize=10, y=0.95)
    
    # 保存为bytes
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', facecolor='#0a0e14', edgecolor='none')
    buf.seek(0)
    plt.close(fig)
    
    img_bytes = buf.getvalue()
    
    if save_to:
        with open(save_to, 'wb') as f:
            f.write(img_bytes)
        print(f"[Topomap] 已保存: {save_to}")
    
    return img_bytes


def topomap_to_base64(img_bytes: bytes) -> str:
    """将图片bytes转为base64字符串"""
    return base64.b64encode(img_bytes).decode('utf-8')


def generate_topomap_base64(values: dict, **kwargs) -> str:
    """生成topomap并返回base64字符串(方便WebSocket传输)"""
    img_bytes = generate_topomap(values, **kwargs)
    return topomap_to_base64(img_bytes)


def generate_topomap_from_array(
    channel_values: list,  # [v0, v1, v2, ...]
    n_channels: int = None,
    channel_names: list = None,
    **kwargs
) -> bytes:
    """
    从通道值数组生成topomap（自动匹配电极位置）
    
    Args:
        channel_values: 通道值列表
        n_channels: 通道数(自动推断)
        channel_names: 电极名列表(可选)
    """
    if n_channels is None:
        n_channels = len(channel_values)
    
    names = get_electrode_names(n_channels, channel_names)
    values = {names[i]: v for i, v in enumerate(channel_values[:len(names)])}
    
    return generate_topomap(values, **kwargs)


def generate_topomap_base64_from_array(channel_values: list, **kwargs) -> str:
    """从通道数组生成base64 topomap"""
    img_bytes = generate_topomap_from_array(channel_values, **kwargs)
    return topomap_to_base64(img_bytes)


# 测试
if __name__ == '__main__':
    # 模拟alpha功率分布
    test_values = {
        'Fp1': 120.5, 'Fp2': 98.2,
        'F7': 85.3, 'F8': 78.9,
        'F3': 150.2, 'F4': 135.7,
        'Fz': 142.0,
        'C3': 95.4, 'C4': 88.1,
        'Cz': 105.3,
        'P3': 110.7, 'P4': 102.4,
        'Pz': 115.8,
        'O1': 180.2, 'O2': 175.5,
    }
    
    img = generate_topomap(test_values, title="Alpha Power (8-13 Hz)", save_to="test_topomap.png")
    print(f"✅ Topomap生成成功: {len(img)} bytes")
    print(f"   保存为: test_topomap.png")
    
    # base64测试
    b64 = topomap_to_base64(img)
    print(f"   Base64长度: {len(b64)} 字符")
