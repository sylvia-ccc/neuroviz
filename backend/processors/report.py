"""
NeuroViz 专业分析报告导出
PDF报告 + CSV原始数据
"""

import numpy as np
import io
import base64
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List


def export_csv(data: np.ndarray, channels: list, fs: int, output_path: str):
    """导出CSV文件"""
    n_ch, n_samp = data.shape
    t = np.arange(n_samp) / fs
    with open(output_path, "w") as f:
        f.write(f"# NeuroViz EEG Export\n")
        f.write(f"# Time: {datetime.now().isoformat()}\n")
        f.write(f"# Sampling Rate: {fs} Hz\n")
        f.write(f"# Channels: {n_ch}\n")
        f.write(f"# Duration: {n_samp/fs:.1f} s\n")
        f.write("Time(s)," + ",".join(channels) + "\n")
        for i in range(n_samp):
            row = [f"{t[i]:.3f}"] + [f"{data[ch, i]:.2f}" for ch in range(n_ch)]
            f.write(",".join(row) + "\n")
    print(f"[Report] CSV导出成功: {output_path}")
    return output_path


# ============ 品牌色 ============
BRAND = {
    "dark": "#121826",
    "purple": "#7B61FF",
    "gold": "#C8B388",
    "light_blue": "#8AA6C2",
    "white": "#FFFFFF",
}

BAND_COLORS = {
    "delta": "#6366F1",  # 靛蓝
    "theta": "#8B5CF6",  # 紫
    "alpha": "#7B61FF",  # 品牌紫
    "beta":  "#C8B388",  # 鎏金
    "gamma": "#F87171",  # 红
}

BAND_NAMES_CN = {
    "delta": "δ (0.5-4Hz)",
    "theta": "θ (4-8Hz)",
    "alpha": "α (8-13Hz)",
    "beta":  "β (13-30Hz)",
    "gamma": "γ (30-50Hz)",
}


def export_pdf(
    data: np.ndarray,
    features: dict,
    output_path: str,
    fs: int = 500,
    channel_names: Optional[List[str]] = None,
    channel_bands: Optional[List[dict]] = None,
    artifact_summary: Optional[dict] = None,
    session_duration_sec: Optional[float] = None,
    topomap_b64: Optional[str] = None,
    spectrogram_b64: Optional[str] = None,
) -> str:
    """
    导出专业PDF分析报告（中文+品牌+图表）
    
    Parameters:
        data: (n_channels, n_samples) 原始EEG数据
        features: emotion_engine输出特征
        output_path: 输出路径
        fs: 采样率
        channel_names: 通道名列表
        channel_bands: 各通道频段功率
        artifact_summary: 伪迹检测汇总 {blink:N, eog:N, emg:N, movement:N}
        session_duration_sec: 会话时长
        topomap_b64: Topomap base64图片
        spectrogram_b64: 频谱图base64图片
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import cm, mm
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
            Image, PageBreak, HRFlowable, KeepTogether,
        )
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        raise RuntimeError("需要reportlab: pip install reportlab")

    # ---- 注册中文字体 ----
    _register_chinese_fonts()

    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    styles = getSampleStyleSheet()
    story = []

    # ---- 自定义样式 ----
    style_title = ParagraphStyle(
        "CNTitle",
        fontName="STHeiti", fontSize=22, leading=28,
        textColor=colors.HexColor(BRAND["purple"]),
        spaceAfter=6, alignment=TA_CENTER,
    )
    style_subtitle = ParagraphStyle(
        "CNSubtitle",
        fontName="STHeiti", fontSize=10, leading=14,
        textColor=colors.HexColor("#666666"),
        spaceAfter=12,
    )
    style_h2 = ParagraphStyle(
        "CNH2",
        fontName="STHeiti", fontSize=14, leading=20,
        textColor=colors.HexColor(BRAND["dark"]),
        spaceBefore=14, spaceAfter=6,
    )
    style_body = ParagraphStyle(
        "CNBody",
        fontName="STHeiti", fontSize=10, leading=16,
        textColor=colors.HexColor("#333333"),
    )
    style_small = ParagraphStyle(
        "CNSmall",
        fontName="STHeiti", fontSize=8, leading=12,
        textColor=colors.HexColor("#999999"),
    )

    # ============ 封面区 ============
    story.append(Paragraph("NeuroViz 脑电分析报告", style_title))
    now = datetime.now()
    story.append(Paragraph(
        f"生成时间：{now.strftime('%Y年%m月%d日 %H:%M')} ｜ NOWIS 脑译斯科技",
        style_subtitle,
    ))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor(BRAND["purple"])))
    story.append(Spacer(1, 0.5*cm))

    # ============ 基本信息卡 ============
    n_ch = data.shape[0]
    duration = session_duration_sec or (data.shape[1] / fs)
    ch_names = channel_names or [f"Ch{i}" for i in range(n_ch)]

    info_rows = [
        ["📋 采集信息", ""],
        ["通道数", f"{n_ch} 通道"],
        ["通道名", "、".join(ch_names[:8]) + ("..." if n_ch > 8 else "")],
        ["采样率", f"{fs} Hz"],
        ["时长", f"{duration:.1f} 秒"],
        ["数据点", f"{data.shape[1]:,}"],
    ]
    _add_table(story, info_rows, col_widths=[4*cm, 12*cm])

    # ============ 情绪分析 ============
    if features:
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("🧠 情绪状态分析", style_h2))

        arousal = features.get("arousal", 0)
        valence = features.get("valence", 0)
        focus = features.get("focus", 0)
        relaxation = features.get("relaxation", 0)

        # 情绪状态判断
        emotion_label = _classify_emotion(arousal, valence)
        focus_label = "高专注" if focus > 0.6 else "中等专注" if focus > 0.3 else "低专注"

        emotion_rows = [
            ["指标", "数值", "状态"],
            ["唤醒度 (Arousal)", f"{arousal:.2f}", "高唤醒" if arousal > 0.6 else "低唤醒"],
            ["效价 (Valence)", f"{valence:.2f}", "积极" if valence > 0.3 else "消极" if valence < -0.3 else "中性"],
            ["情绪分类", emotion_label, ""],
            ["专注度", f"{focus:.2f}", focus_label],
            ["放松度", f"{relaxation:.2f}", "深度放松" if relaxation > 0.7 else "一般" if relaxation > 0.3 else "紧张"],
        ]
        _add_table(story, emotion_rows, col_widths=[4*cm, 4*cm, 4*cm], header_row=1)

    # ============ 频段能量分析 ============
    bands_data = None
    if "bands_ch1" in features:
        bands_data = features["bands_ch1"]
    elif channel_bands and len(channel_bands) > 0:
        # 合并所有通道的平均频段
        avg = {}
        for band in ["delta", "theta", "alpha", "beta", "gamma"]:
            avg[band] = float(np.mean([ch.get(band, 0) for ch in channel_bands]))
        bands_data = avg

    if bands_data:
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("⚡ 频段能量分析", style_h2))

        total_power = sum(bands_data.values()) or 1
        band_rows = [["频段", "功率 (µV²)", "占比", "主要功能"]]
        band_functions = {
            "delta": "深睡、无意识",
            "theta": "冥想、创意",
            "alpha": "放松、闭眼",
            "beta":  "专注、思考",
            "gamma": "高级认知",
        }
        for band in ["delta", "theta", "alpha", "beta", "gamma"]:
            power = bands_data.get(band, 0)
            pct = power / total_power * 100
            band_rows.append([
                BAND_NAMES_CN.get(band, band),
                f"{power:.2f}",
                f"{pct:.1f}%",
                band_functions.get(band, ""),
            ])
        _add_table(story, band_rows, col_widths=[4*cm, 3*cm, 3*cm, 5*cm], header_row=1)

        # 频段柱状图（matplotlib生成）
        try:
            bar_b64 = _generate_band_bar_chart(bands_data)
            if bar_b64:
                story.append(Spacer(1, 0.3*cm))
                img = _b64_to_image(bar_b64, width=14*cm, height=5*cm)
                if img:
                    story.append(img)
        except Exception as e:
            print(f"[Report] 频段柱状图生成失败: {e}")

    # ============ 多通道频段（如果有） ============
    if channel_bands and len(channel_bands) > 1:
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("📊 多通道频段对比", style_h2))

        ch_band_rows = [["通道"] + [BAND_NAMES_CN.get(b, b) for b in ["delta","theta","alpha","beta","gamma"]]]
        for i, ch in enumerate(channel_bands[:8]):
            name = ch_names[i] if i < len(ch_names) else f"Ch{i}"
            ch_band_rows.append([name] + [f"{ch.get(b, 0):.1f}" for b in ["delta","theta","alpha","beta","gamma"]])
        _add_table(story, ch_band_rows, col_widths=[2.5*cm]+[2.5*cm]*5, header_row=1)

    # ============ 脑地形图 ============
    if topomap_b64:
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("🗺️ 脑地形图 (Alpha Power)", style_h2))
        img = _b64_to_image(topomap_b64, width=10*cm, height=10*cm)
        if img:
            story.append(img)

    # ============ 频谱图 ============
    if spectrogram_b64:
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("🌈 时频分析", style_h2))
        img = _b64_to_image(spectrogram_b64, width=14*cm, height=6*cm)
        if img:
            story.append(img)

    # ============ 伪迹检测报告 ============
    if artifact_summary:
        story.append(Spacer(1, 0.4*cm))
        story.append(Paragraph("⚠️ 伪迹检测报告", style_h2))
        total_art = sum(artifact_summary.values())
        if total_art == 0:
            story.append(Paragraph("✅ 信号质量良好，未检测到显著伪迹", style_body))
        else:
            art_rows = [["伪迹类型", "检测次数", "影响程度", "建议"]]
            severity = {"blink": "低", "eog": "低-中", "emg": "中", "movement": "高"}
            tips = {
                "blink": "眨眼伪迹常见，可使用ICA去除",
                "eog": "减少眼球转动，或使用独立成分分析",
                "emg": "放松面部和颈部肌肉",
                "movement": "采集时保持静止，检查电极接触",
            }
            type_cn = {"blink": "👁️ 眨眼", "eog": "👀 眼动", "emg": "💪 肌电", "movement": "🚶 移动"}
            for atype, count in artifact_summary.items():
                art_rows.append([
                    type_cn.get(atype, atype),
                    str(count),
                    severity.get(atype, "未知"),
                    tips.get(atype, ""),
                ])
            _add_table(story, art_rows, col_widths=[3*cm, 3*cm, 3*cm, 6*cm], header_row=1)

    # ============ 波形缩略图 ============
    try:
        waveform_b64 = _generate_waveform_thumbnail(data, fs, ch_names)
        if waveform_b64:
            story.append(Spacer(1, 0.4*cm))
            story.append(Paragraph("📈 波形缩略图", style_h2))
            img = _b64_to_image(waveform_b64, width=14*cm, height=6*cm)
            if img:
                story.append(img)
    except Exception as e:
        print(f"[Report] 波形缩略图生成失败: {e}")

    # ============ 页脚 ============
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CCCCCC")))
    story.append(Paragraph(
        f"© {now.year} NOWIS 脑译斯科技 ｜ NeuroViz v1.0 ｜ 本报告仅供参考，不构成医疗诊断依据",
        style_small,
    ))

    # ---- 生成PDF ----
    doc.build(story)
    print(f"[Report] PDF导出成功: {output_path}")
    return output_path


# ============ 辅助函数 ============

def _register_chinese_fonts():
    """注册中文字体（macOS系统字体）"""
    from reportlab.pdfbase import pdfmetrics as _pm
    from reportlab.pdfbase.ttfonts import TTFont as _TF
    font_paths = [
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/System/Library/Fonts/STHeiti Light.ttc',
        '/System/Library/Fonts/Supplemental/Songti.ttc',
    ]
    for path in font_paths:
        try:
            _pm.registerFont(_TF('STHeiti', path, subfontIndex=0))
            _pm.registerFont(_TF('STHeiti-Bold', path, subfontIndex=0))
            _pm.registerFont(_TF('STHeiti-Italic', path, subfontIndex=0))
            _pm.registerFont(_TF('STHeiti-BoldItalic', path, subfontIndex=0))
            _pm.registerFontFamily('STHeiti', normal='STHeiti', bold='STHeiti-Bold', italic='STHeiti-Italic', boldItalic='STHeiti-BoldItalic')
            return
        except Exception:
            continue
    try:
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        _pm.registerFont(UnicodeCIDFont('STSong-Light'))
        _pm.registerFontFamily('STSong-Light', normal='STSong-Light', bold='STSong-Light')
    except Exception:
        pass


def _add_table(story, rows, col_widths=None, header_row=0):
    """添加带样式的表格"""
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    tbl = Table(rows, colWidths=col_widths)
    style_cmds = [
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "STHeiti"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
    ]
    if header_row:
        style_cmds += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(BRAND["dark"])),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "STHeiti"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
        ]
    # 交替行背景
    for i in range(header_row, len(rows)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#F8F9FA")))
    tbl.setStyle(TableStyle(style_cmds))
    story.append(tbl)


def _classify_emotion(arousal: float, valence: float) -> str:
    """Russell情绪四象限分类"""
    if arousal > 0.3:
        return "兴奋/愉悦" if valence > 0.1 else "焦虑/紧张"
    else:
        return "平静/满足" if valence > 0.1 else "疲倦/低落"


def _b64_to_image(b64_str: str, width=None, height=None):
    """base64字符串转reportlab Image"""
    from reportlab.platypus import Image as RLImage
    try:
        # 去掉可能的data:image/png;base64,前缀
        if "," in b64_str:
            b64_str = b64_str.split(",", 1)[1]
        img_bytes = base64.b64decode(b64_str)
        buf = io.BytesIO(img_bytes)
        kwargs = {}
        if width: kwargs["width"] = width
        if height: kwargs["height"] = height
        return RLImage(buf, **kwargs)
    except Exception as e:
        print(f"[Report] 图片解码失败: {e}")
        return None


def _generate_band_bar_chart(bands_data: dict) -> Optional[str]:
    """生成频段能量柱状图"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        bands = ["delta", "theta", "alpha", "beta", "gamma"]
        values = [bands_data.get(b, 0) for b in bands]
        bar_colors = [BAND_COLORS[b] for b in bands]
        labels = [BAND_NAMES_CN[b] for b in bands]

        fig, ax = plt.subplots(figsize=(7, 2.5))
        bars = ax.bar(labels, values, color=bar_colors, width=0.6, edgecolor="white", linewidth=0.5)
        ax.set_ylabel("功率 (µV²)", fontsize=9)
        ax.set_title("频段能量分布", fontsize=11, fontweight="bold")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(labelsize=8)

        # 添加数值标签
        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width()/2, bar.get_height(),
                        f"{val:.1f}", ha="center", va="bottom", fontsize=7)

        plt.tight_layout()
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[Report] 柱状图生成失败: {e}")
        return None


def _generate_waveform_thumbnail(data: np.ndarray, fs: int, ch_names: list) -> Optional[str]:
    """生成波形缩略图"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        n_ch = min(data.shape[0], 8)
        # 最多显示10秒
        max_samples = min(data.shape[1], fs * 10)
        t = np.arange(max_samples) / fs

        fig, axes = plt.subplots(n_ch, 1, figsize=(7, n_ch * 0.8 + 1), sharex=True)
        if n_ch == 1:
            axes = [axes]

        for i in range(n_ch):
            ax = axes[i]
            sig = data[i, :max_samples]
            # 归一化显示
            std = np.std(sig) or 1
            ax.plot(t, sig / std, linewidth=0.3, color=BRAND["purple"])
            ax.set_ylabel(ch_names[i] if i < len(ch_names) else f"Ch{i}", fontsize=7, rotation=0, labelpad=30)
            ax.set_yticks([])
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.spines["left"].set_visible(False)

        axes[-1].set_xlabel("时间 (s)", fontsize=8)
        fig.suptitle("EEG 波形缩略图", fontsize=10, fontweight="bold")
        plt.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        print(f"[Report] 波形缩略图生成失败: {e}")
        return None
