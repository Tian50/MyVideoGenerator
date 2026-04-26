import subprocess
import os
import re
from pathlib import Path
import pysubs2
from PIL import ImageFont, ImageDraw, Image

def get_video_dimensions(video_path):
    """获取视频宽度和高度（像素）"""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height", "-of", "csv=p=0",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"无法获取视频尺寸: {result.stderr}")
    width, height = map(int, result.stdout.strip().split(','))
    return width, height

def get_video_pix_fmt(video_path):
    """获取原始视频的像素格式"""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=pix_fmt", "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return "yuv420p"
    return result.stdout.strip()

def get_video_frame_rate(video_path):
    """获取原始视频帧率（作为字符串，如 '25' 或 '30000/1001'）"""
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=r_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1",
        video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return "25"
    return result.stdout.strip()

def get_text_width(text, font_path, font_size):
    """计算给定文本在指定字体、字号下的像素宽度"""
    try:
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()
    img = Image.new('RGB', (1, 1))
    draw = ImageDraw.Draw(img)
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]

def split_text_to_fit(text, font_path, font_size, max_width, margin=20, max_lines=3):
    """
    将文本拆分成多行（最多 max_lines 行，中间用 \\N 分隔），
    保证每一行的像素宽度 ≤ max_width - margin。
    如果无法在 max_lines 行内完全容纳，则逐步缩小字体（最小为原大小的 70%）。
    最后仍超限则截断并加省略号，确保不会出现被静默裁剪的不完整字幕。
    """
    effective_max_width = max_width - margin
    original_font_size = font_size

    def get_width(t, fs):
        return get_text_width(t, font_path, fs)

    # 贪心分行：按字符逐一添加，保证每行不超过最大宽度
    def greedy_split(line, fs):
        if get_width(line, fs) <= effective_max_width:
            return [line]
        chars = list(line)  # 按字符分割（中文、英文均适用）
        lines = []
        current_line = ""
        for ch in chars:
            test_line = current_line + ch
            if get_width(test_line, fs) <= effective_max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = ch
        if current_line:
            lines.append(current_line)
        return lines

    # 尝试原始字号及逐步缩小
    for shrink_factor in [1.0, 0.9, 0.8, 0.7]:
        current_fs = int(original_font_size * shrink_factor)
        if current_fs < 12:
            break
        lines = greedy_split(text, current_fs)
        if len(lines) <= max_lines:
            if shrink_factor < 1.0:
                print(f"⚠️ 字幕过长，自动缩小字体为 {current_fs}px（原 {original_font_size}px）")
            return "\\N".join(lines)

    # 保底：强行截断到最大行数，并截断最后一行（加省略号）
    lines = greedy_split(text, original_font_size)[:max_lines]
    if len(lines) == max_lines and get_width(lines[-1], original_font_size) > effective_max_width:
        last_line = lines[-1]
        truncated = ""
        for ch in last_line:
            if get_width(truncated + ch, original_font_size) <= effective_max_width - get_width("…", original_font_size):
                truncated += ch
            else:
                break
        lines[-1] = truncated + "…"
    return "\\N".join(lines)

def embed_subtitles(video_path, chinese_srt, english_srt, output_path,
                    font_path=None, cn_margin=80, en_margin=30,
                    encoder="libx264", include_original=True, lossless=True):
    """
    将中英文字幕烧录到视频中（硬编码），并自动对中文字幕进行换行（若超出视频宽度）
    若 lossless=True，则使用 libx264 -crf 0 无损编码，极大保留原视频细节（文件巨大）
    """
    # 获取原始视频属性
    video_width, video_height = get_video_dimensions(video_path)
    original_pix_fmt = get_video_pix_fmt(video_path)
    original_framerate = get_video_frame_rate(video_path)
    print(f"视频尺寸: {video_width}x{video_height}")
    print(f"原始像素格式: {original_pix_fmt}, 帧率: {original_framerate}")

    # 读取字幕
    cn_subs = pysubs2.load(str(chinese_srt), encoding="utf-8")
    if include_original:
        en_subs = pysubs2.load(str(english_srt), encoding="utf-8")

    # 字体名称
    if font_path and os.path.exists(font_path):
        font_name = Path(font_path).stem
    else:
        font_name = "SimHei"
        font_path = None

    # 样式定义（不再使用 wraptype，改用全局 WrapStyle=1）
    cn_style = pysubs2.SSAStyle(
        fontname=font_name,
        fontsize=60,
        primarycolor=pysubs2.Color(255, 222, 0),
        outlinecolor=pysubs2.Color(0, 0, 0, 80),
        backcolor=pysubs2.Color(0, 0, 0, 0),
        bold=False,
        italic=False,
        outline=4,
        alignment=2,
        marginv=cn_margin
    )
    if include_original:
        en_style = pysubs2.SSAStyle(
            fontname="Arial",
            fontsize=45,
            primarycolor=pysubs2.Color(183, 220, 246),
            outlinecolor=pysubs2.Color(0, 0, 0, 80),
            backcolor=pysubs2.Color(0, 0, 0, 0),
            bold=False,
            italic=False,
            outline=8,
            alignment=2,
            marginv=en_margin
        )

    cn_subs.styles["Chinese"] = cn_style
    for event in cn_subs.events:
        event.style = "Chinese"

    if include_original:
        en_subs.styles["English"] = en_style
        for event in en_subs.events:
            event.style = "English"

    # 自动换行（仅中文），增加安全边距
    if font_path and os.path.exists(font_path):
        max_width = video_width - 80   # 原为 40，增加安全余量
        font_size = cn_style.fontsize
        for event in cn_subs.events:
            clean_text = re.sub(r'\{.*?\}', '', event.text)
            new_text = split_text_to_fit(clean_text, font_path, font_size, max_width, margin=20, max_lines=3)
            if new_text != clean_text:
                event.text = new_text
                print(f"自动换行: {clean_text} -> {new_text}")
    else:
        print("⚠️ 未提供有效字体文件路径，跳过中文字幕自动换行")

    # 合并事件
    if include_original:
        all_events = list(cn_subs.events) + list(en_subs.events)
    else:
        all_events = list(cn_subs.events)
    all_events.sort(key=lambda e: e.start)
    merged = pysubs2.SSAFile()
    merged.styles.update(cn_subs.styles)
    if include_original:
        merged.styles.update(en_subs.styles)
    merged.events = all_events

    merged.info["PlayResX"] = video_width
    merged.info["PlayResY"] = video_height
    # 设置全局换行样式：1 表示仅使用 \N 换行，禁止自动换行（兼容旧版 pysubs2）
    merged.info["WrapStyle"] = "1"

    center_x = video_width // 2
    for event in merged.events:
        if event.style == "Chinese":
            y = video_height - cn_margin
            event.text = f"{{\\an(2)\\pos({center_x}, {y})}}{event.text}"
        elif event.style == "English" and include_original:
            y = video_height - en_margin
            event.text = f"{{\\an(2)\\pos({center_x}, {y})}}{event.text}"

    temp_dir = Path("temp_ass")
    temp_dir.mkdir(exist_ok=True)
    ass_path = temp_dir / f"subs_{os.getpid()}.ass"
    merged.save(str(ass_path))
    ass_rel = str(ass_path).replace("\\", "/")
    print(f"ASS 文件: {ass_rel}")

    # 构造 FFmpeg 命令
    vf = f"ass={ass_rel}"
    cmd = [
        "ffmpeg", "-i", video_path,
        "-vf", vf,
        "-c:a", "copy",
        "-y", output_path
    ]

    if lossless:
        cmd.extend(["-c:v", "libx264", "-preset", "veryslow", "-crf", "0"])
        cmd.extend(["-r", original_framerate])
        try:
            cmd.extend(["-pix_fmt", original_pix_fmt])
        except:
            cmd.extend(["-pix_fmt", "yuv420p"])
        cmd.extend(["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"])
    else:
        if encoder == "h264_nvenc":
            cmd.extend(["-c:v", "h264_nvenc", "-preset", "p6", "-rc", "vbr", "-cq", "16"])
        elif encoder == "h264_qsv":
            cmd.extend(["-c:v", "h264_qsv", "-preset", "fast", "-cq", "16"])
        elif encoder == "h264_amf":
            cmd.extend(["-c:v", "h264_amf", "-quality", "speed", "-cq", "16"])
        else:
            cmd.extend(["-c:v", "libx264", "-preset", "medium", "-crf", "18"])
        cmd.extend(["-r", original_framerate])

    print("执行命令:", " ".join(cmd))
    try:
        subprocess.run(cmd, check=True)
        print(f"✅ 字幕烧录成功: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"❌ FFmpeg 错误: {e}")
        raise
    finally:
        if ass_path.exists():
            ass_path.unlink()
        try:
            temp_dir.rmdir()
        except OSError:
            pass

def embed_subtitles_auto(video_path, srt_base_path, output_path, font_path=None,
                         cn_margin=80, en_margin=30, encoder="libx264",
                         include_original=True, lossless=True):
    """
    硬编码模式：将字幕烧录进视频，输出 MP4 文件。
    若 lossless=True，则使用无损编码（文件巨大但画质无损）。
    """
    base = Path(srt_base_path)
    english_srt = base
    chinese_srt = base.parent / f"{base.stem}_zh{base.suffix}"
    if not english_srt.exists():
        raise FileNotFoundError(f"英文字幕不存在: {english_srt}")
    if not chinese_srt.exists():
        raise FileNotFoundError(f"中文字幕不存在: {chinese_srt}")

    final_output = Path(output_path).with_suffix('.mp4')
    if final_output.exists() and final_output.stat().st_size > 0:
        print(f"⏭️ 字幕文件已存在: {final_output}，跳过处理")
        return str(final_output)

    embed_subtitles(video_path, str(chinese_srt), str(english_srt), str(final_output),
                    font_path, cn_margin, en_margin, encoder, include_original, lossless)
    return str(final_output)


# 示例调用（可根据需要注释或修改）
if __name__ == "__main__":
    # 使用示例
    # embed_subtitles_auto(
    #     video_path="input.mp4",
    #     srt_base_path="subtitle.srt",   # 英文字幕路径，中文自动在同目录找 subtitle_zh.srt
    #     output_path="output.mp4",
    #     font_path="simhei.ttf",         # 中文字体文件路径
    #     cn_margin=80,
    #     en_margin=30,
    #     lossless=True                   # 无损编码
    # )
    pass