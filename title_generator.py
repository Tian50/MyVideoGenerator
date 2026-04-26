import requests
import time
import json
import re
from prompts_config import PromptManager

def generate_titles_from_srt(srt_path, api_key, video_metadata=None, original_title=None, max_retries=2):
    """
    读取整个中文字幕文件（SRT），发送给 DeepSeek API 生成标题建议，
    返回一个包含最多 20 个标题和对应时间戳的列表。
    每个元素格式：{"title": "标题", "timestamp": "起始时间-结束时间"}
    :param video_metadata: dict, 包含 'author', 'upload_date', 'subscribers', 'view_count', 'like_count',
                            'blogger_nationality', 'blogger_gender', 'blogger_nickname' 等
    :param original_title: str, 视频原标题（可选），作为参考
    """
    with open(srt_path, "r", encoding="utf-8") as f:
        srt_content = f.read()

    # 构建原始标题描述
    title_ref = ""
    if original_title:
        title_ref = f"视频原标题（仅供参考，请勿直接复制）：{original_title}\n"

    # 构建元数据描述文本（包含博主信息）
    meta_desc = ""
    if video_metadata:
        parts = []
        author = video_metadata.get('author', '')
        subscribers = video_metadata.get('subscribers', '')
        view_count = video_metadata.get('view_count', 0)
        like_count = video_metadata.get('like_count', 0)
        upload_date = video_metadata.get('upload_date', '')
        # 博主信息
        blogger_nationality = video_metadata.get('blogger_nationality', '')
        blogger_gender = video_metadata.get('blogger_gender', '')
        blogger_nickname = video_metadata.get('blogger_nickname', '')
        
        if author:
            parts.append(f"博主：{author}")
        if blogger_nationality:
            parts.append(f"国籍：{blogger_nationality}")
        if blogger_gender:
            parts.append(f"性别：{blogger_gender}")
        if blogger_nickname:
            parts.append(f"中文外号：{blogger_nickname}")
        if subscribers and subscribers != '未知':
            parts.append(f"粉丝数：{subscribers}")
        if view_count:
            parts.append(f"本视频播放量：{view_count}")
        if like_count:
            parts.append(f"点赞数：{like_count}")
        if upload_date:
            parts.append(f"发布日期：{upload_date}")
        if parts:
            meta_desc = "视频元数据：" + "，".join(parts) + "。"

    # 使用配置文件的提示词
    base_prompt = PromptManager.get_title_generation_prompt()
    prompt = base_prompt.format(title_ref=title_ref, meta_desc=meta_desc) + f"""

字幕内容：
{srt_content}

请输出 JSON 数组："""

    # 获取API配置
    api_config = PromptManager.get_api_config("title_generation")
    retry_config = PromptManager.get_retry_config()
    
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": api_config.get("model", "deepseek-chat"),
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": api_config.get("temperature", 0.8),
                    "max_tokens": api_config.get("max_tokens", 2500)
                },
                timeout=retry_config.get("timeout", 60)
            )
            if response.status_code != 200:
                raise Exception(f"API 请求失败: {response.status_code} - {response.text}")
            content = response.json()["choices"][0]["message"]["content"].strip()

            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', content)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content

            data = json.loads(json_str)
            if isinstance(data, list) and all(isinstance(item, dict) and 'title' in item for item in data):
                result = []
                for item in data[:20]:
                    result.append({
                        "title": item.get("title", ""),
                        "timestamp": item.get("timestamp", "")
                    })
                return result
            else:
                if isinstance(data, list) and all(isinstance(t, str) for t in data):
                    return [{"title": t, "timestamp": ""} for t in data[:20]]
                else:
                    return []
        except Exception as e:
            print(f"生成标题失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return []
            time.sleep(retry_config.get("backoff_factor", 2) ** attempt)
    return []