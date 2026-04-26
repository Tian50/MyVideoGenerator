# content_filter.py


import os
import re
import subprocess
import json
from pathlib import Path
from typing import List, Tuple, Dict, Any
import requests
from prompts_config import PromptManager

def parse_srt(srt_path: str) -> List[Dict[str, Any]]:
    """解析 SRT 文件，返回列表，每个元素包含 index, start, end, text"""
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()
    blocks = re.split(r'\n\s*\n', content.strip())
    subtitles = []
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        idx = lines[0]
        time_line = lines[1]
        text = ' '.join(lines[2:])
        start_str, end_str = time_line.split(' --> ')
        start_sec = time_to_seconds(start_str.replace(',', '.'))
        end_sec = time_to_seconds(end_str.replace(',', '.'))
        subtitles.append({
            'index': int(idx),
            'start': start_sec,
            'end': end_sec,
            'text': text
        })
    return subtitles

def time_to_seconds(t: str) -> float:
    parts = t.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h)*3600 + int(m)*60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m)*60 + float(s)
    else:
        return float(t)

def seconds_to_time_str(sec: float) -> str:
    """将秒数转换为 SRT 时间格式 HH:MM:SS,mmm"""
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = sec % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace('.', ',')

def detect_violation_intervals(subtitles: List[Dict[str, Any]], api_key: str) -> List[Tuple[float, float]]:
    """
    调用 DeepSeek API 分析整个字幕，找出包含广告或违规内容的连续时间段。
    返回需要切除的区间列表（秒为单位）。
    """
    # 构建带时间戳的字幕文本
    transcript = []
    for sub in subtitles:
        start_str = seconds_to_time_str(sub['start'])
        end_str = seconds_to_time_str(sub['end'])
        transcript.append(f"[{start_str} --> {end_str}] {sub['text']}")
    full_text = "\n".join(transcript)

        # 使用配置文件的提示词
    base_prompt = PromptManager.get_content_filter_prompt()
    prompt = base_prompt + f"""

字幕内容：
{full_text}
"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 500
    }
    response = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, headers=headers)
    if response.status_code != 200:
        raise Exception(f"API 请求失败: {response.text}")
    result = response.json()
    answer = result['choices'][0]['message']['content'].strip()
    
    # 提取 JSON 数组
    json_match = re.search(r'\[.*\]', answer, re.DOTALL)
    if not json_match:
        print("[content_filter] API 返回无有效区间，视为无违规")
        return []
    try:
        intervals = json.loads(json_match.group())
        result_intervals = []
        for item in intervals:
            start_sec = time_to_seconds(item['start'].replace(',', '.'))
            end_sec = time_to_seconds(item['end'].replace(',', '.'))
            result_intervals.append((start_sec, end_sec))
        return result_intervals
    except Exception as e:
        print(f"[content_filter] 解析返回区间失败: {e}, 原始内容: {answer}")
        return []

def merge_intervals(intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """合并重叠或相邻的区间（间隔小于0.5秒视为相邻）"""
    if not intervals:
        return []
    intervals.sort(key=lambda x: x[0])
    merged = [list(intervals[0])]
    for start, end in intervals[1:]:
        if start - merged[-1][1] <= 0.5:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]

def print_interval_subtitles(subtitles: List[Dict[str, Any]], intervals: List[Tuple[float, float]]):
    """打印每个区间对应的原始字幕内容（原文）"""
    if not intervals:
        return
    print("\n[content_filter] 违规区间对应的原始字幕内容：")
    for idx, (start, end) in enumerate(intervals, 1):
        print(f"\n--- 区间 {idx}: {start:.2f}s -> {end:.2f}s ---")
        # 找出所有与区间重叠的字幕
        for sub in subtitles:
            if sub['end'] >= start and sub['start'] <= end:
                print(f"  序号 {sub['index']}: [{seconds_to_time_str(sub['start'])} --> {seconds_to_time_str(sub['end'])}] {sub['text']}")

def cut_video_by_remove_intervals(input_video: str, remove_intervals: List[Tuple[float, float]], output_video: str) -> bool:
    if not remove_intervals:
        import shutil
        shutil.copy2(input_video, output_video)
        return True

    probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", input_video]
    total_duration = float(subprocess.check_output(probe_cmd).decode().strip())
    
    keep_intervals = []
    last_end = 0.0
    for start, end in remove_intervals:
        if start > last_end:
            keep_intervals.append((last_end, start))
        last_end = max(last_end, end)
    if last_end < total_duration:
        keep_intervals.append((last_end, total_duration))
    
    if not keep_intervals:
        print("⚠️ 整个视频都被标记为违规，将保留原视频")
        import shutil
        shutil.copy2(input_video, output_video)
        return True

    temp_dir = Path("temp_cut")
    temp_dir.mkdir(exist_ok=True)
    temp_files = []
    try:
        for i, (start, end) in enumerate(keep_intervals):
            duration = end - start
            if duration <= 0:
                continue
            temp_file = temp_dir / f"keep_{i}.mp4"
            temp_files.append(temp_file)
            cmd = [
                "ffmpeg", "-ss", str(start), "-i", input_video,
                "-t", str(duration),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-y", str(temp_file)
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"✅ 保留片段 {i+1}: {start:.2f}s -> {end:.2f}s")

        concat_list = temp_dir / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for tf in temp_files:
                abs_path = tf.resolve().as_posix()
                f.write(f"file '{abs_path}'\n")
        cmd_concat = [
            "ffmpeg", "-f", "concat", "-safe", "0", "-i", str(concat_list),
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-y", output_video
        ]
        subprocess.run(cmd_concat, check=True)
        print(f"✅ 违规内容已切除，输出: {output_video}")
        return True
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

def filter_content_by_srt(video_path: str, srt_path: str, api_key: str, output_path: str) -> bool:
    """主函数：根据中文字幕识别违规内容区间并切除"""
    print(f"[content_filter] 开始分析字幕: {srt_path}")
    subtitles = parse_srt(srt_path)
    if not subtitles:
        print("[content_filter] 字幕为空，跳过切除")
        import shutil
        shutil.copy2(video_path, output_path)
        return True

    print(f"[content_filter] 共 {len(subtitles)} 条字幕，正在检测广告/违规区间...")
    remove_intervals = detect_violation_intervals(subtitles, api_key)
    if not remove_intervals:
        print("[content_filter] 未检测到违规区间，直接复制原视频")
        import shutil
        shutil.copy2(video_path, output_path)
        return True

    remove_intervals = merge_intervals(remove_intervals)
    # 打印违规区间对应的字幕内容
    print_interval_subtitles(subtitles, remove_intervals)
    print(f"[content_filter] 需要切除的时间段: {remove_intervals}")
    return cut_video_by_remove_intervals(video_path, remove_intervals, output_path)