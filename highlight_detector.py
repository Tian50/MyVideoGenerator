import json
import re
import time
import requests
from pathlib import Path
from prompts_config import PromptManager

def read_srt_timestamps_and_text(srt_path):
    """
    读取 SRT 文件，返回一个列表，每个元素为 (start, end, text)，
    start/end 为秒数，text 为文本。
    """
    import pysubs2
    subs = pysubs2.load(str(srt_path), encoding="utf-8")
    result = []
    for event in subs:
        result.append((event.start / 1000.0, event.end / 1000.0, event.text))
    return result

def detect_highlight_timestamps_from_srt(srt_path, api_key, num=3, max_retries=2):
    """
    使用 DeepSeek 分析字幕，找出博主享受美食的精彩片段时间轴。
    返回一个列表，每个元素为 (start_sec, end_sec) 元组，每个片段时长不超过20秒。
    """
    # 读取字幕内容
    segments = read_srt_timestamps_and_text(srt_path)
    if not segments:
        raise ValueError("字幕文件为空或解析失败")

    # 将字幕构造成便于模型理解的格式：时间 + 文本（不截断）
    transcript = []
    for start, end, text in segments:
        start_str = f"{int(start//3600):02d}:{int((start%3600)//60):02d}:{int(start%60):02d}"
        end_str = f"{int(end//3600):02d}:{int((end%3600)//60):02d}:{int(end%60):02d}"
        transcript.append(f"[{start_str}->{end_str}] {text}")
    transcript_str = "\n".join(transcript)
    # 不再截断

        # 使用配置文件的提示词
    base_prompt = PromptManager.get_highlight_detection_prompt(num)
    prompt = base_prompt + f"""

字幕内容：
{transcript_str}
"""
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 500
                },
                timeout=60
            )
            if response.status_code != 200:
                raise Exception(f"API 请求失败: {response.status_code} - {response.text}")
            content = response.json()["choices"][0]["message"]["content"].strip()

            # 提取 JSON 数组
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content
            timestamps = json.loads(json_str)
            if isinstance(timestamps, list) and all(isinstance(ts, str) and '-' in ts for ts in timestamps):
                # 转换为秒数，并验证时长
                result = []
                for ts in timestamps[:num]:
                    start_str, end_str = ts.split('-')
                    start_sec = time_to_seconds(start_str.strip())
                    end_sec = time_to_seconds(end_str.strip())
                    duration = end_sec - start_sec
                    if duration > 20:
                        print(f"⚠️ 片段 {ts} 时长 {duration:.1f}s 超过20秒，将截断至20秒")
                        end_sec = start_sec + 20
                    if duration <= 0:
                        print(f"⚠️ 跳过无效片段 {ts}")
                        continue
                    result.append((start_sec, end_sec))
                return result
            else:
                # 回退：尝试从文本中直接提取时间戳
                time_pattern = r'(\d{2}:\d{2}:\d{2})-(\d{2}:\d{2}:\d{2})'
                matches = re.findall(time_pattern, content)
                if matches:
                    result = []
                    for start_str, end_str in matches[:num]:
                        start_sec = time_to_seconds(start_str)
                        end_sec = time_to_seconds(end_str)
                        duration = end_sec - start_sec
                        if duration > 20:
                            end_sec = start_sec + 20
                        if duration > 0:
                            result.append((start_sec, end_sec))
                    return result
                else:
                    raise Exception("无法解析时间戳")
        except Exception as e:
            print(f"高光检测失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return []
            time.sleep(2 ** attempt)
    return []

def time_to_seconds(t_str):
    """将 "HH:MM:SS" 或 "MM:SS" 转换为秒数"""
    parts = t_str.split(':')
    if len(parts) == 3:
        h, m, s = parts
        return int(h)*3600 + int(m)*60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return int(m)*60 + float(s)
    else:
        return float(t_str)