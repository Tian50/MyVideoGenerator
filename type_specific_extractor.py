import os
from pathlib import Path
import subprocess
from typing import List, Dict, Optional
import json

def extract_type_specific_clips(
    video_path: str,
    srt_path: str,
    api_key: str,
    output_path: str,
    video_category: str
) -> str:
    """
    根据视频类型提取特定内容片段
    
    参数:
        video_path: 输入视频路径
        srt_path: 字幕文件路径
        api_key: DeepSeek API密钥
        output_path: 输出视频路径
        video_category: 视频类型 (interview/political)
        
    返回:
        输出视频路径
    """
    print(f"⏳ 开始提取{video_category}视频的特定片段...")
    
    # 1. 读取字幕文件
    with open(srt_path, 'r', encoding='utf-8') as f:
        srt_content = f.read()
    
    # 2. 分析字幕，找出目标片段
    segments = analyze_subtitle_for_specific_content(srt_content, api_key, video_category)
    
    if not segments:
        print("⚠️ 未找到符合条件的片段，将返回原视频")
        return video_path
    
    # 3. 提取片段并合并
    temp_dir = Path(output_path).parent / "temp_clips"
    temp_dir.mkdir(exist_ok=True)
    
    clip_paths = []
    for i, segment in enumerate(segments):
        clip_path = temp_dir / f"clip_{i}.mp4"
        extract_video_segment(video_path, segment['start'], segment['end'], str(clip_path))
        clip_paths.append(str(clip_path))
    
    # 合并片段
    concat_videos(clip_paths, output_path)
    
    # 清理临时文件
    for clip in clip_paths:
        Path(clip).unlink()
    temp_dir.rmdir()
    
    return output_path

def analyze_subtitle_for_specific_content(
    srt_content: str,
    api_key: str,
    video_category: str
) -> List[Dict[str, float]]:
    """
    分析字幕内容，找出贬低自己国家、夸赞中国的片段
    
    参数:
        srt_content: 字幕内容
        api_key: DeepSeek API密钥
        video_category: 视频类型
        
    返回:
        包含start和end时间的片段列表
    """
    import requests
    import re
    from typing import List, Dict
    
    # 1. 解析SRT文件获取时间戳和文本
    srt_entries = []
    pattern = re.compile(r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.+?)(?=\n\n|\n\d+\n|$)', re.DOTALL)
    matches = pattern.findall(srt_content)
    
    for match in matches:
        _, start, end, text = match
        # 转换时间格式为秒
        start_sec = sum(x * float(t) for x, t in zip([3600, 60, 1], start.replace(',', '.').split(':')))
        end_sec = sum(x * float(t) for x, t in zip([3600, 60, 1], end.replace(',', '.').split(':')))
        srt_entries.append({
            'start': start_sec,
            'end': end_sec,
            'text': text.replace('\n', ' ')
        })
    
    # 2. 构建API请求
    url = "https://api.deepseek.com/v1/analyze"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # 根据视频类型设置不同的提示词
    if video_category == "interview":
        prompt = """请严格分析以下访谈视频字幕，精确找出以下两类内容：
1. 受访者贬低自己国家(包括但不限于:批评政府、贬低文化、否定成就等)
2. 受访者明确夸赞中国(包括但不限于:赞扬发展、肯定政策、欣赏文化等)

要求：
1. 只返回明确符合上述条件的片段
2. 每个片段至少持续30秒，确保有完整上下文（原20秒改为30秒）
3. 相邻相关片段间隔小于10秒的合并为一个片段
4. 保留片段前后各5秒作为上下文
5. 确保片段长度合理，不要做成短混剪
6. 返回格式：[{"start": 开始时间秒, "end": 结束时间秒, "reason": "具体分析原因"}]"""
    else:  # political
        prompt = """请严格分析以下政治评论视频字幕，精确找出以下两类内容：
1. 评论者贬低自己国家(包括但不限于:否定体制、批评政策、唱衰经济等) 
2. 评论者明确夸赞中国(包括但不限于:肯定成就、赞扬制度、欣赏发展等)

要求：
1. 只返回明确符合上述条件的片段
2. 每个片段至少持续45秒，确保有完整论述（原30秒改为45秒）
3. 相邻相关片段间隔小于10秒的合并为一个片段  
4. 保留片段前后各5秒作为上下文
5. 确保片段长度合理，不要做成短混剪
6. 返回格式：[{"start": 开始时间秒, "end": 结束时间秒, "reason": "具体分析原因"}]"""
    
    # 3. 分批发送请求(避免过长)
    segments = []
    batch_size = 5  # 每次分析5个片段
    for i in range(0, len(srt_entries), batch_size):
        batch = srt_entries[i:i+batch_size]
        data = {
            "prompt": prompt,
            "context": "\n\n".join([f"{entry['start']}-{entry['end']}s: {entry['text']}" for entry in batch]),
            "max_tokens": 1000
        }
        
        try:
            response = requests.post(url, headers=headers, json=data)
            if response.status_code == 200:
                result = response.json()
                if isinstance(result, list):
                    segments.extend(result)
        except Exception as e:
            print(f"⚠️ API分析失败: {e}")
            continue
    
    # 4. 合并相邻片段并处理视频开头/结尾
    if not segments:
        return []
        
    # 按开始时间排序
    segments = sorted(segments, key=lambda x: x['start'])
    
    # 处理第一个片段之前的部分
    if segments[0]['start'] > 0:
        segments.insert(0, {
            'start': 0,
            'end': segments[0]['start'],
            'reason': '前置无关内容'
        })
    
    # 合并中间片段并扩展上下文
    merged_segments = []
    for seg in segments:
        if not merged_segments:
            # 扩展开始时间，保留5秒上下文
            seg['start'] = max(0, seg['start'] - 5)
            merged_segments.append(seg)
        else:
            last = merged_segments[-1]
            if seg['start'] - last['end'] < 10:  # 如果间隔小于10秒则合并
                # 确保合并后片段长度合理
                if (seg['end'] + 5 - last['start']) <= 300:  # 最大不超过5分钟
                    last['end'] = seg['end'] + 5  # 扩展结束时间，保留5秒上下文
                    last['reason'] += f"; {seg['reason']}"
                else:
                    # 如果合并后太长，则作为新片段处理
                    last['end'] = min(last['end'] + 5, seg['start'])
                    seg['start'] = max(last['end'], seg['start'] - 5)
                    merged_segments.append(seg)
            else:
                # 扩展前一个片段的结束时间
                last['end'] = min(last['end'] + 5, seg['start'])
                # 扩展当前片段的开始时间
                seg['start'] = max(last['end'], seg['start'] - 5)
                merged_segments.append(seg)
    
    # 处理最后一个片段之后的部分
    last_segment = merged_segments[-1]
    if last_segment['end'] < srt_entries[-1]['end']:
        merged_segments.append({
            'start': last_segment['end'],
            'end': srt_entries[-1]['end'],
            'reason': '后置无关内容'
        })
    
    # 只保留目标片段(过滤掉标记为无关内容的片段)
    target_segments = [
        seg for seg in merged_segments 
        if '无关内容' not in seg['reason']
    ]
    
    return [{"start": s['start'], "end": s['end']} for s in target_segments]

def extract_video_segment(
    input_path: str,
    start_time: float,
    end_time: float,
    output_path: str
) -> None:
    """
    提取视频片段
    
    参数:
        input_path: 输入视频路径
        start_time: 开始时间(秒)
        end_time: 结束时间(秒)
        output_path: 输出路径
    """
    duration = end_time - start_time
    cmd = [
        'ffmpeg',
        '-y',
        '-ss', str(start_time),
        '-i', input_path,
        '-t', str(duration),
        '-c:v', 'libx264',
        '-c:a', 'aac',
        '-strict', 'experimental',
        output_path
    ]
    subprocess.run(cmd, check=True)

def concat_videos(input_paths: List[str], output_path: str) -> None:
    """
    合并多个视频片段
    
    参数:
        input_paths: 输入视频路径列表
        output_path: 输出路径
    """
    # 生成文件列表
    list_file = Path(output_path).parent / "concat_list.txt"
    with open(list_file, 'w', encoding='utf-8') as f:
        for path in input_paths:
            f.write(f"file '{Path(path).absolute()}'\n")
    
    cmd = [
        'ffmpeg',
        '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', str(list_file),
        '-c', 'copy',
        output_path
    ]
    subprocess.run(cmd, check=True)
    list_file.unlink()