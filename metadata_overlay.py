import subprocess
import os
from pathlib import Path

def format_number(num):
    try:
        return f"{int(num):,}"
    except:
        return str(num)

def get_video_properties(video_path):
    """获取视频的帧率、像素格式、色彩信息等"""
    # 获取帧率
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    framerate = result.stdout.strip() if result.returncode == 0 else "25"
    # 获取像素格式
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=pix_fmt", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    pix_fmt = result.stdout.strip() if result.returncode == 0 else "yuv420p"
    # 获取色彩参数
    cmd = ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=color_primaries,color_trc,colorspace", "-of", "default=noprint_wrappers=1:nokey=1", video_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    color_info = result.stdout.strip().split('\n') if result.returncode == 0 else []
    color_primaries = color_info[0] if len(color_info) > 0 else "bt709"
    color_trc = color_info[1] if len(color_info) > 1 else "bt709"
    colorspace = color_info[2] if len(color_info) > 2 else "bt709"
    return framerate, pix_fmt, color_primaries, color_trc, colorspace

def add_metadata_to_video(video_path, metadata, output_path, font_path, use_gpu=True, duration=8, lossless=True):
    """
    直接将元数据叠加到整个视频上（不切割），适用于短视频片段。
    字幕只显示前 duration 秒，之后不再显示。
    若 lossless=True，使用 libx264 -crf 0 无损编码，极大保留画质（文件巨大）。
    """
    lines = []
    if metadata.get('author'):
        lines.append(f"作者：{metadata['author']}")
    if metadata.get('upload_date'):
        lines.append(f"发布时间：{metadata['upload_date']}")
    if metadata.get('subscribers'):
        lines.append(f"粉丝量：{format_number(metadata['subscribers'])}")
    if metadata.get('view_count'):
        lines.append(f"播放量：{format_number(metadata['view_count'])}")
    if metadata.get('like_count'):
        lines.append(f"点赞数：{format_number(metadata['like_count'])}")
    lines.append("翻译：老外逛吃中国")
    
    if not lines:
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

    temp_dir = Path("temp_meta")
    temp_dir.mkdir(exist_ok=True)
    ass_file = temp_dir / f"metadata_{os.getpid()}.ass"
    
    font_name = Path(font_path).stem
    primary_color = "&H00FFFF00"   # 青色
    outline_color = "&H00000000"   # 黑色描边
    back_color = "&H00000000"      # 透明背景
    
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},62,{primary_color},{primary_color},{outline_color},{back_color},0,0,0,0,100,100,0,0,1,3,0,7,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    text_lines = "\\N".join(lines)
    ass_content += f"Dialogue: 0,0:00:00.00,0:00:{duration:02d}.00,Default,,0,0,0,,{text_lines}"

    with open(ass_file, "w", encoding="utf-8") as f:
        f.write(ass_content)

    try:
        if lossless:
            # 无损模式：获取原始视频属性，强制使用 libx264 -crf 0
            framerate, pix_fmt, color_primaries, color_trc, colorspace = get_video_properties(video_path)
            print(f"无损模式：帧率={framerate}, 像素格式={pix_fmt}, 色彩参数={color_primaries}/{color_trc}/{colorspace}")
            cmd = [
                "ffmpeg", "-i", video_path,
                "-vf", f"ass={ass_file.as_posix()}",
                "-c:v", "libx264",
                "-preset", "veryslow",
                "-crf", "0",
                "-r", framerate,
                "-pix_fmt", pix_fmt,
                "-color_primaries", color_primaries,
                "-color_trc", color_trc,
                "-colorspace", colorspace,
                "-c:a", "copy",
                "-y", output_path
            ]
        else:
            # 非无损模式（使用 GPU 或默认编码）
            if use_gpu:
                encoder = "h264_nvenc"
                encoder_args = ["-preset", "p6", "-rc", "vbr", "-cq", "18"]
            else:
                encoder = "libx264"
                encoder_args = ["-preset", "medium", "-crf", "23"]
            cmd = [
                "ffmpeg", "-i", video_path,
                "-vf", f"ass={ass_file.as_posix()}",
                "-c:v", encoder, *encoder_args,
                "-c:a", "copy",
                "-y", output_path
            ]
        subprocess.run(cmd, check=True)
        print(f"✅ 元数据已叠加到视频上{'（无损）' if lossless else ''}，输出: {output_path}")
        return output_path
    finally:
        if ass_file.exists():
            ass_file.unlink()
        try:
            temp_dir.rmdir()
        except OSError:
            pass

def add_metadata_to_start(video_path, metadata, output_path, font_path, use_gpu=True, duration=8, lossless=True):
    """
    将元数据信息添加到视频开头（前 duration 秒）。
    优化：仅重新编码前 duration 秒，其余部分流拷贝。
    若 lossless=True，前 duration 秒使用无损编码（libx264 -crf 0），其余流拷贝。
    """
    lines = []
    if metadata.get('author'):
        lines.append(f"作者：{metadata['author']}")
    if metadata.get('upload_date'):
        lines.append(f"发布时间：{metadata['upload_date']}")
    if metadata.get('subscribers'):
        lines.append(f"粉丝量：{format_number(metadata['subscribers'])}")
    if metadata.get('view_count'):
        lines.append(f"播放量：{format_number(metadata['view_count'])}")
    if metadata.get('like_count'):
        lines.append(f"点赞数：{format_number(metadata['like_count'])}")
    lines.append("翻译：红豆泥tube")
    
    if not lines:
        import shutil
        shutil.copy2(video_path, output_path)
        return output_path

    temp_dir = Path("temp_meta")
    temp_dir.mkdir(exist_ok=True)
    ass_file = temp_dir / f"metadata_{os.getpid()}.ass"
    
    font_name = Path(font_path).stem
    primary_color = "&H00FFFF00"
    outline_color = "&H00000000"
    back_color = "&H00000000"
    
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},62,{primary_color},{primary_color},{outline_color},{back_color},0,0,0,0,100,100,0,0,1,3,0,7,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    text_lines = "\\N".join(lines)
    ass_content += f"Dialogue: 0,0:00:00.00,0:00:{duration:02d}.00,Default,,0,0,0,,{text_lines}"

    with open(ass_file, "w", encoding="utf-8") as f:
        f.write(ass_content)

    try:
        # 获取原始视频的时间基准（仅用于无损模式）
        if lossless:
            framerate, pix_fmt, color_primaries, color_trc, colorspace = get_video_properties(video_path)
            print(f"无损模式：帧率={framerate}, 像素格式={pix_fmt}")

        # 1. 提取前 duration 秒（流拷贝）
        first_part = temp_dir / "first_part.mp4"
        cmd_first = [
            "ffmpeg", "-i", video_path,
            "-t", str(duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            "-y", str(first_part)
        ]
        subprocess.run(cmd_first, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 2. 提取剩余部分（流拷贝）
        second_part = temp_dir / "second_part.mp4"
        cmd_second = [
            "ffmpeg", "-i", video_path,
            "-ss", str(duration),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            "-y", str(second_part)
        ]
        subprocess.run(cmd_second, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 3. 对前 duration 秒添加元数据
        first_with_meta = temp_dir / "first_with_meta.mp4"
        if lossless:
            # 无损编码
            cmd_meta = [
                "ffmpeg", "-i", str(first_part),
                "-vf", f"ass={ass_file.as_posix()}",
                "-c:v", "libx264",
                "-preset", "veryslow",
                "-crf", "0",
                "-r", framerate,
                "-pix_fmt", pix_fmt,
                "-color_primaries", color_primaries,
                "-color_trc", color_trc,
                "-colorspace", colorspace,
                "-c:a", "copy",
                "-y", str(first_with_meta)
            ]
        else:
            # 非无损：使用软件编码或 GPU
            if use_gpu:
                encoder = "h264_nvenc"
                encoder_args = ["-preset", "p6", "-rc", "vbr", "-cq", "18"]
            else:
                encoder = "libx264"
                encoder_args = ["-preset", "medium", "-crf", "23"]
            cmd_meta = [
                "ffmpeg", "-i", str(first_part),
                "-vf", f"ass={ass_file.as_posix()}",
                "-c:v", encoder, *encoder_args,
                "-c:a", "copy",
                "-y", str(first_with_meta)
            ]
        subprocess.run(cmd_meta, check=True)

        # 4. 拼接两部分（流拷贝）
        concat_list = temp_dir / "concat.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            f.write(f"file '{first_with_meta.resolve().as_posix()}'\n")
            f.write(f"file '{second_part.resolve().as_posix()}'\n")
        cmd_concat = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            "-y", output_path
        ]
        subprocess.run(cmd_concat, check=True)

        print(f"✅ 元数据已添加至开头{'（无损）' if lossless else ''}，输出: {output_path}")
        return output_path
    finally:
        for f in [ass_file, temp_dir / "first_part.mp4", temp_dir / "second_part.mp4",
                  temp_dir / "first_with_meta.mp4", temp_dir / "concat.txt"]:
            if f.exists():
                f.unlink()
        try:
            temp_dir.rmdir()
        except OSError:
            pass