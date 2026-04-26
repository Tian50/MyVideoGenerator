"""
视频来源类型分类模块
根据视频作者信息、部分字幕内容、原视频标题，调用 DeepSeek API 判断视频来源类型：
- news_media: 新闻媒体/电视台
- political_show: 政论节目
- political_blogger: 个人键政博主
"""

import requests
import json
import re
import time
from prompts_config import PromptManager


def classify_video(author_info: str, subtitle_sample: str, original_title: str, api_key: str, max_retries: int = 2) -> dict:
    """
    调用 DeepSeek API 判断视频的来源类型。

    :param author_info: 视频作者信息（如频道名称、作者名等）
    :param subtitle_sample: 部分字幕内容（前若干条字幕即可，用于分析内容风格）
    :param original_title: 原视频标题
    :param api_key: DeepSeek API 密钥
    :param max_retries: 最大重试次数
    :return: dict，格式如：
        {
            "category": "news_media" | "political_show" | "political_blogger",
            "reason": "简短分析理由",
            "status": "success"
        }
        如果失败，返回 {"status": "failed", "error": "错误信息"}
    """
    if not author_info and not original_title and not subtitle_sample:
        return {"status": "failed", "error": "缺少足够的输入信息（作者信息、标题、字幕内容均为空）"}

    # 从配置获取提示词
    base_prompt = PromptManager.get_video_classifier_prompt()

    # 构建输入信息
    input_parts = []
    if original_title:
        input_parts.append(f"【视频标题】\n{original_title}")
    if author_info:
        input_parts.append(f"【作者/频道信息】\n{author_info}")
    if subtitle_sample:
        # 截取前 1500 字符作为字幕样本，避免超出 token 限制
        sample = subtitle_sample[:1500]
        input_parts.append(f"【字幕内容样本（前段）】\n{sample}")

    user_input = "\n\n".join(input_parts)

    prompt = f"{base_prompt}\n\n以下是需要分析的视频信息：\n\n{user_input}"

    # 获取API配置
    api_config = PromptManager.get_api_config("video_classifier")
    retry_config = PromptManager.get_retry_config()

    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": api_config.get("model", "deepseek-chat"),
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": api_config.get("temperature", 0.1),
                    "max_tokens": api_config.get("max_tokens", 300)
                },
                timeout=retry_config.get("timeout", 60)
            )

            if response.status_code != 200:
                raise Exception(f"API请求失败: {response.status_code} - {response.text}")

            content = response.json()["choices"][0]["message"]["content"].strip()

            # 提取 JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if not json_match:
                raise Exception("API返回内容中未找到有效的JSON")

            result = json.loads(json_match.group())

            category = result.get("category", "")
            reason = result.get("reason", "")

            # 验证分类结果是否合法
            valid_categories = ["news_media", "political_show", "political_blogger"]
            if category not in valid_categories:
                raise Exception(f"返回的分类 '{category}' 不在有效范围内: {valid_categories}")

            return {
                "category": category,
                "reason": reason,
                "status": "success"
            }

        except Exception as e:
            print(f"⚠️ 视频分类失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return {"status": "failed", "error": str(e)}
            time.sleep(retry_config.get("backoff_factor", 2) ** attempt)

    return {"status": "failed", "error": "未知错误"}


def get_category_display_name(category: str) -> str:
    """将分类标识符转换为可读的中文名称"""
    display_names = {
        "news_media": "新闻媒体/电视台",
        "political_show": "政论节目",
        "political_blogger": "个人键政博主"
    }
    return display_names.get(category, f"未知类型({category})")


# ========== 使用示例 ==========
if __name__ == "__main__":
    # 简单测试
    test_author = "BBC News"
    test_title = "China's economy: What's next for the world's second-largest economy?"
    test_subtitle = "Welcome to BBC News. Today we're looking at China's economic outlook..."
    
    # 这个测试需要环境中有 DEEPSEEK_API_KEY
    import os
    from dotenv import load_dotenv
    load_dotenv()
    
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        result = classify_video(test_author, test_subtitle, test_title, api_key)
        print("分类结果:", result)
        if result.get("status") == "success":
            print(f"类型: {get_category_display_name(result['category'])}")
            print(f"理由: {result['reason']}")
    else:
        print("请先设置 DEEPSEEK_API_KEY 环境变量")
