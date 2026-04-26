import requests
import json
import re
import time
from prompts_config import PromptManager

def get_blogger_info(metadata, api_key, max_retries=2):
    """
    根据metadata中的作者名字，通过DeepSeek API查询博主的国籍、性别、中文外号等信息
    
    :param metadata: dict, 包含 'author' 字段的视频元数据
    :param api_key: DeepSeek API密钥
    :param max_retries: 最大重试次数
    :return: dict, 包含博主信息的字典，例如:
        {
            "nationality": "美国",
            "gender": "男",
            "chinese_nickname": "铁蛋哥",
            "status": "success"
        }
        如果查询失败，返回 {"status": "failed", "error": "..."}
    """
    author_name = metadata.get('author', '')
    if not author_name:
        return {"status": "failed", "error": "metadata中未提供作者名称"}
    
    prompt = f"""请根据以下外国博主的名称，搜索并返回该博主的个人信息：
- 博主名称：{author_name}
- 信息类型：国籍、性别、在中国互联网上的中文外号/昵称

请以JSON格式返回，格式如下：
{{"nationality": "国籍", "gender": "性别", "chinese_nickname": "中文外号"}}


如果某条信息无法找到，对应的值请留空字符串。
只输出JSON，不要有其他内容。"""

    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 200
                },
                timeout=30
            )
            if response.status_code != 200:
                raise Exception(f"API请求失败: {response.status_code} - {response.text}")
            
            content = response.json()["choices"][0]["message"]["content"].strip()
            
            # 提取JSON
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                # 确保返回的字段都存在
                return {
                    "nationality": result.get("nationality", ""),
                    "gender": result.get("gender", ""),
                    "chinese_nickname": result.get("chinese_nickname", ""),
                    "status": "success"
                }
            else:
                return {"status": "failed", "error": "无法解析API返回的JSON"}
                
        except Exception as e:
            print(f"⚠️ 查询博主信息失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return {"status": "failed", "error": str(e)}
            time.sleep(2 ** attempt)
    
    return {"status": "failed", "error": "未知错误"}

def merge_blogger_info_to_metadata(metadata, blogger_info):
    """
    将查询到的博主信息合并到原有的metadata中
    
    :param metadata: 原始视频元数据
    :param blogger_info: get_blogger_info 返回的博主信息字典
    :return: 合并后的新metadata字典
    """
    new_metadata = metadata.copy()
    if blogger_info.get("status") == "success":
        new_metadata["blogger_nationality"] = blogger_info.get("nationality", "")
        new_metadata["blogger_gender"] = blogger_info.get("gender", "")
        new_metadata["blogger_nickname"] = blogger_info.get("chinese_nickname", "")
    else:
        new_metadata["blogger_nationality"] = ""
        new_metadata["blogger_gender"] = ""
        new_metadata["blogger_nickname"] = ""
    return new_metadata