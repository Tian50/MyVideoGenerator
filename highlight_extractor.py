import subprocess
import shutil
from pathlib import Path
import os

def time_to_seconds(t):
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, str):
        t = t.strip()
        if ':' in t:
            parts = t.split(':')
            if len(parts) == 3:
                h, m, s = parts
                return int(h)*3600 + int(m)*60 + float(s)
            elif len(parts) == 2:
                m, s = parts
                return int(m)*60 + float(s)
        else:
            return float(t)
    return 0.0

def extract_and_prepend_highlights(original_video_path, segments, output_path, use_gpu=True):
    if not segments:
        shutil.copy2(original_video_path, output_path)
        return

    temp_dir = Path("temp_clips")
    temp_dir.mkdir(exist_ok=True)
    temp_files = []

    try:
        # 1. 提取高光片段（流拷贝 + 时间戳修正）
        for i, (start, end) in enumerate(segments):
            start_sec = time_to_seconds(start)
            end_sec = time_to_seconds(end)
            duration = end_sec - start_sec
            if duration <= 0:
                continue

            clip_path = temp_dir / f"highlight_{i}.mp4"
            temp_files.append(clip_path)
            cmd = [
                "ffmpeg", "-ss", str(start_sec), "-i", original_video_path,
                "-t", str(duration),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                "-y", str(clip_path)
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"✅ 提取片段 {i+1}: {start} -> {end}")

        if not temp_files:
            shutil.copy2(original_video_path, output_path)
            return

        # 2. 拼接所有高光片段（流拷贝 + 时间戳修正）
        concat_list = temp_dir / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for clip in temp_files:
                f.write(f"file '{clip.resolve().as_posix()}'\n")
        all_highlights = temp_dir / "all_highlights.mp4"
        cmd_concat = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            "-y", str(all_highlights)
        ]
        subprocess.run(cmd_concat, check=True)

        # 3. 合并高光片段与原视频（流拷贝 + 时间戳修正）
        final_concat = temp_dir / "final_concat.txt"
        with open(final_concat, "w", encoding="utf-8") as f:
            f.write(f"file '{all_highlights.resolve().as_posix()}'\n")
            f.write(f"file '{Path(original_video_path).resolve().as_posix()}'\n")
        cmd_final = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(final_concat),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            "-y", output_path
        ]
        subprocess.run(cmd_final, check=True)
        print(f"✅ 高光片段已添加至片头，输出: {output_path}")

    finally:
        for f in temp_files:
            if f.exists():
                f.unlink()
        for f in [temp_dir / "all_highlights.mp4", temp_dir / "concat_list.txt", temp_dir / "final_concat.txt"]:
            if f.exists():
                f.unlink()
        try:
            temp_dir.rmdir()
        except OSError:
            pass

def extract_highlights_by_timestamps(original_video_path, timestamps, output_path, use_gpu=True):
    extract_and_prepend_highlights(original_video_path, timestamps, output_path, use_gpu)

def extract_highlights_clip(original_video_path, segments, output_path, use_gpu=True):
    """
    仅提取高光片段并拼接成一个独立的视频文件（流拷贝 + 时间戳修正）
    """
    if not segments:
        return None

    abs_original = os.path.abspath(original_video_path)
    abs_output = os.path.abspath(output_path)
    output_dir = os.path.dirname(abs_output)
    os.makedirs(output_dir, exist_ok=True)

    temp_dir = Path(output_dir) / "temp_highlights_clip"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_files = []
    concat_list = temp_dir / "concat_list.txt"

    try:
        for i, (start, end) in enumerate(segments):
            start_sec = time_to_seconds(start)
            end_sec = time_to_seconds(end)
            duration = end_sec - start_sec
            if duration <= 0:
                continue

            clip_path = temp_dir / f"highlight_{i:03d}.mp4"
            temp_files.append(clip_path)
            cmd = [
                "ffmpeg", "-ss", str(start_sec), "-i", abs_original,
                "-t", str(duration),
                "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                "-fflags", "+genpts",
                "-y", str(clip_path)
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"✅ 提取高光片段 {i+1}: {start} -> {end}")

        if not temp_files:
            return None

        with open(concat_list, "w", encoding="utf-8") as f:
            for clip in temp_files:
                f.write(f"file '{clip.resolve().as_posix()}'\n")

        cmd_concat = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            "-fflags", "+genpts",
            "-y", abs_output
        ]
        subprocess.run(cmd_concat, check=True)
        print(f"✅ 高光片头视频已生成: {abs_output}")
        return abs_output

    except subprocess.CalledProcessError as e:
        print(f"❌ 高光片头生成失败: {e}")
        raise
    finally:
        for f in temp_files:
            if f.exists():
                f.unlink()
        if concat_list.exists():
            concat_list.unlink()
        try:
            temp_dir.rmdir()
        except OSError:
            pass

def concat_videos(video_paths, output_path, use_gpu=True):
    """拼接多个视频文件（流拷贝 + 时间戳修正）"""
    if not video_paths:
        raise ValueError("没有提供任何视频片段")
    if len(video_paths) == 1:
        shutil.copy2(video_paths[0], output_path)
        return output_path

    output_dir = os.path.dirname(os.path.abspath(output_path))
    temp_dir = Path(output_dir) / "temp_concat"
    temp_dir.mkdir(parents=True, exist_ok=True)
    concat_list = temp_dir / "concat_list.txt"

    with open(concat_list, "w", encoding="utf-8") as f:
        for vp in video_paths:
            abs_path = os.path.abspath(vp).replace("\\", "/")
            f.write(f"file '{abs_path}'\n")

    cmd = [
        "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_list),
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        "-fflags", "+genpts",
        "-y", output_path
    ]
    subprocess.run(cmd, check=True)

    concat_list.unlink()
    temp_dir.rmdir()
    return output_path