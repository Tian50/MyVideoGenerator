"""
提示词配置文件
将所有AI提示词集中管理，便于修改和调整
"""

# ========== API 配置 ==========
class APIConfig:
    """API配置参数"""
    
    # DeepSeek API 配置
    DEEPSEEK_CONFIG = {
        "translation": {
            "model": "deepseek-chat",
            "temperature": 0.3,
            "max_tokens": 2000
        },
        "correction": {
            "model": "deepseek-chat",
            "temperature": 0,
            "max_tokens": 1000
        },
        "title_generation": {
            "model": "deepseek-chat",
            "temperature": 0.8,
            "max_tokens": 2500
        },
        "blogger_info": {
            "model": "deepseek-chat",
            "temperature": 0.3,
            "max_tokens": 200
        },
        "highlight_detection": {
            "model": "deepseek-chat",
            "temperature": 0.3,
            "max_tokens": 500
        },
        "content_filter": {
            "model": "deepseek-chat",
            "temperature": 0,
            "max_tokens": 500
        },
        "title_split": {
            "model": "deepseek-chat",
            "temperature": 0.3,
            "max_tokens": 150
        },
        "video_classifier": {
            "model": "deepseek-chat",
            "temperature": 0.1,
            "max_tokens": 300
        }
    }
    
    # 重试配置
    RETRY_CONFIG = {
        "max_retries": 3,
        "backoff_factor": 2,  # 指数退避因子
        "timeout": 60  # 请求超时时间（秒）
    }


# ========== 翻译模块提示词 ==========
class TranslatorPrompts:
    """翻译模块的提示词"""
    
    @staticmethod
    def get_translation_prompt(target_lang="zh"):
        """翻译字幕的提示词"""
        return f"""将以下英文字幕翻译成{target_lang}。请以 JSON 数组形式返回，每个元素包含 "index" 和 "translation" 两个字段。示例：[{{"index": 1, "translation": "你好"}}]。
不要输出任何其他内容。"""

    @staticmethod
    def get_correction_prompt():
        """检查翻译质量的提示词"""
        return """请检查以下字幕翻译的质量。要求：
1. 重点关注！序号不能错乱，一句对应一句。这个非常非常非常重要！一定要按序号核对！不要有序号2的译文对应原文序号1或者3这样的情况！！！
2. 译文必须是目标语言（中文），不能出现整句话都是英文或原文语言，有一两个单词是英文专用词可以。
3. 译文语义基本正确，没有明显错误。
{history}
如果发现有问题，请返回一个 JSON 数组，每个元素包含 "index" 和 "correction" 两个字段，例如：
[{{"index": 3, "correction": "修正后的中文翻译"}}, ...]
只返回需要修正的条目。如果全部正确，返回空数组 []。
不要输出任何其他内容。"""


# ========== 标题生成模块提示词 ==========
class TitleGeneratorPrompts:
    """标题生成模块的提示词"""
    
    @staticmethod
    def get_title_generation_prompt():
        """生成视频标题的提示词"""
        return """{title_ref}{meta_desc}
下面的是视频字幕文本，请为这个视频起 **20 个**吸引人的标题（必须返回 20 个，不能少）。
观众画像："观看日媒对中国相关报道，希望看到日媒在中国面前贬低自己并被中国的强大实力吓到的人"，但注意不要出现"文化自信"和"赢"这些字。
最好突出中国比其他国家强大的地方，让看视频的中国观众有优越感的地方，这是重点！
标题尽量口语化一点，或者带点网络年轻人的习惯用词或网络热梗，比如"吓傻了"，"头皮发麻"，"幽默完了，"哎不对不对"，"闹麻了"，"红豆泥私密马赛"，"tm"，"锐评"，尽量不要让人感觉有AI味儿，因为观众都是年轻人。
在每个标题后要一个时间：需要一个和标题适配的时间点

请直接返回一个 JSON 数组，每个元素是一个对象，包含 "title" 和 "timestamp" 两个字段。例如：
[
  {{"title": "标题1", "timestamp": "00:01:23"}},
  {{"title": "标题2", "timestamp": "00:03:10"}}
]
不要有其他文字。"""


# ========== 博主信息查询模块提示词 ==========
class BloggerInfoPrompts:
    """博主信息查询模块的提示词"""
    
    @staticmethod
    def get_blogger_info_prompt():
        """查询博主信息的提示词"""
        return """请根据以下外国博主的名称，搜索并返回该博主的个人信息：
- 博主名称：{author_name}
- 信息类型：国籍、性别、在中国互联网上的中文外号/昵称

请以JSON格式返回，格式如下：
{{"nationality": "国籍", "gender": "性别", "chinese_nickname": "中文外号"}}

如果某条信息无法找到，对应的值请留空字符串。
只输出JSON，不要有其他内容。"""


# ========== 高光检测模块提示词 ==========
class HighlightDetectorPrompts:
    """高光检测模块的提示词"""
    
    @staticmethod
    def get_highlight_detection_prompt(num=3):
        """检测高光片段的提示词"""
        return f"""你是一个视频编辑助手。下面是一段美食视频的字幕文本（包含时间戳和说话内容）。请找出其中 **博主夸赞中国** 的 {num} 个精彩片段。

要求：
1. 每个片段是一个时间区间，格式为 "HH:MM:SS-HH:MM:SS"。
2. 每个片段的时长 **不超过20秒**。
3. 返回一个 JSON 数组，例如：["00:01:23-00:01:45", "00:05:10-00:05:25", "00:12:03-00:12:18"]。
4. 只返回 JSON 数组，不要有其他文字。"""


# ========== 内容过滤模块提示词 ==========
class ContentFilterPrompts:
    """内容过滤模块的提示词"""
    
    @staticmethod
    def get_content_filter_prompt():
        """检测违规内容的提示词"""
        return """你是一个视频内容审核助手。请分析以下视频的字幕文本，找出其中**包含广告推广内容**（例如：突然介绍不相关的产品、链接、联系方式、促销信息、赞助内容）、**政治敏感内容,特别是提到习近平三个字**或**与中国无关的内容**的**连续时间段**。

要求：
- 广告通常是连续的一段话，可能跨越多条字幕。请找出每个这样的连续时间段。
- 只返回广告/违规内容的**开始和结束时间**（使用字幕中给出的时间格式 HH:MM:SS,mmm）。
- 如果没有发现任何违规，返回空数组 []。
- 如果有多段违规，返回多个区间。
- 输出格式：JSON 数组，每个元素是一个对象，包含 "start" 和 "end" 两个字段，例如：
  [{"start": "00:01:23,456", "end": "00:01:35,789"}, ...]
- 不要有其他解释文字。"""


# ========== 视频分类模块提示词 ==========
class VideoClassifierPrompts:
    """视频分类模块的提示词"""
    
    @staticmethod
    def get_video_classifier_prompt():
        """判断视频来源类型的提示词"""
        return """你是一个专业的视频内容分析师。请根据以下信息判断这个视频的来源类型。

你需要判断的类型包括：
1. **新闻媒体/电视台**（news_media）：如NHK、朝日新闻、CNN、BBC等正规新闻媒体或电视台的报道
2. **政论节目**（political_show）：如电视政论节目、座谈会、访谈节目等，通常有多位嘉宾讨论政治话题
3. **个人键政博主**（political_blogger）：个人自媒体博主，主要发表政治观点评论的

请综合分析以下维度：
- 视频标题、作者名称是否带有新闻媒体/电视台特征
- 字幕内容中是否有新闻播报风格、多嘉宾讨论氛围、或个人观点输出
- 内容涉及的话题性质和讨论方式

以JSON格式返回分析结果：
{{"category": "news_media|political_show|political_blogger", "reason": "简短的分析理由（20字以内）"}}

只输出JSON，不要有其他内容。"""


# ========== 封面生成模块提示词 ==========
class CoverGeneratorPrompts:
    """封面生成模块的提示词"""
    
    @staticmethod
    def get_cover_design_prompt():
        """封面设计助手提示词（用于火山引擎）"""
        return """在图片中添加大字标题'{title_text}'，这个标题可以拆分为2-3段，每一段独立占一行
排版要求：左右两边1/4宽度的地方不能有文字，字体样式要足够醒目，色彩鲜艳，好看
每一行字体要不一样，一张图用2-3种字体，一张图里的字不要只用一种字体
排版要合理，突出主题，有镜头语言"""

    @staticmethod
    def get_title_split_prompt():
        """标题分段提示词（用于DeepSeek）"""
        return """你是一个封面设计助手。请将以下标题拆分成 2-3 行，每行尽量简短、有节奏感，适合放在视频封面的底部或中部。
要求：
- 每行不超过 12 个汉字
- 保持语义完整
- 只返回 JSON 数组，例如：["第一行", "第二行", "第三行"]
- 不要有其他解释文字

标题：{title_text}"""


# ========== 提示词管理器 ==========
class PromptManager:
    """提示词管理器，提供统一的访问接口"""
    
    @staticmethod
    def get_api_config(task_type):
        """获取API配置"""
        return APIConfig.DEEPSEEK_CONFIG.get(task_type, {})
    
    @staticmethod
    def get_retry_config():
        """获取重试配置"""
        return APIConfig.RETRY_CONFIG
    
    @staticmethod
    def get_translation_prompt(target_lang="zh"):
        return TranslatorPrompts.get_translation_prompt(target_lang)
    
    @staticmethod
    def get_correction_prompt():
        return TranslatorPrompts.get_correction_prompt()
    
    @staticmethod
    def get_title_generation_prompt():
        return TitleGeneratorPrompts.get_title_generation_prompt()
    
    @staticmethod
    def get_blogger_info_prompt():
        return BloggerInfoPrompts.get_blogger_info_prompt()
    
    @staticmethod
    def get_highlight_detection_prompt(num=3):
        return HighlightDetectorPrompts.get_highlight_detection_prompt(num)
    
    @staticmethod
    def get_content_filter_prompt():
        return ContentFilterPrompts.get_content_filter_prompt()
    
    @staticmethod
    def get_cover_design_prompt():
        return CoverGeneratorPrompts.get_cover_design_prompt()
    
    @staticmethod
    def get_title_split_prompt():
        return CoverGeneratorPrompts.get_title_split_prompt()
    
    @staticmethod
    def get_video_classifier_prompt():
        return VideoClassifierPrompts.get_video_classifier_prompt()


# ========== 配置验证工具 ==========
class ConfigValidator:
    """配置验证工具"""
    
    @staticmethod
    def validate_all_configs():
        """验证所有配置"""
        errors = []
        
        # 验证API配置
        for task_type, config in APIConfig.DEEPSEEK_CONFIG.items():
            if not config.get("model"):
                errors.append(f"API配置 '{task_type}' 缺少 model 字段")
            if config.get("temperature") is None:
                errors.append(f"API配置 '{task_type}' 缺少 temperature 字段")
            if not config.get("max_tokens"):
                errors.append(f"API配置 '{task_type}' 缺少 max_tokens 字段")
        
        # 验证重试配置
        retry_config = APIConfig.RETRY_CONFIG
        if not retry_config.get("max_retries"):
            errors.append("重试配置缺少 max_retries 字段")
        if retry_config.get("backoff_factor") is None:
            errors.append("重试配置缺少 backoff_factor 字段")
        if not retry_config.get("timeout"):
            errors.append("重试配置缺少 timeout 字段")
        
        # 验证提示词
        test_cases = [
            ("翻译提示词", PromptManager.get_translation_prompt),
            ("修正提示词", PromptManager.get_correction_prompt),
            ("标题生成提示词", PromptManager.get_title_generation_prompt),
            ("博主信息提示词", PromptManager.get_blogger_info_prompt),
            ("高光检测提示词", lambda: PromptManager.get_highlight_detection_prompt(3)),
            ("内容过滤提示词", PromptManager.get_content_filter_prompt),
            ("封面设计提示词", PromptManager.get_cover_design_prompt),
            ("标题分段提示词", PromptManager.get_title_split_prompt),
            ("视频分类提示词", PromptManager.get_video_classifier_prompt),
        ]
        
        for name, func in test_cases:
            try:
                result = func()
                if not result or not isinstance(result, str):
                    errors.append(f"{name} 返回无效值")
            except Exception as e:
                errors.append(f"{name} 调用失败: {e}")
        
        return errors


# ========== 使用示例 ==========
if __name__ == "__main__":
    # 示例：如何使用提示词和配置
    pm = PromptManager()
    
    print("=== 配置验证 ===")
    errors = ConfigValidator.validate_all_configs()
    if errors:
        print("❌ 配置验证失败:")
        for error in errors:
            print(f"  - {error}")
    else:
        print("✅ 所有配置验证通过")
    
    print("\n=== API配置示例 ===")
    print("翻译API配置:", pm.get_api_config("translation"))
    print("标题生成API配置:", pm.get_api_config("title_generation"))
    print("重试配置:", pm.get_retry_config())
    
    print("\n=== 提示词示例 ===")
    print("翻译提示词前50字符:", pm.get_translation_prompt()[:50] + "...")
    print("标题生成提示词前50字符:", pm.get_title_generation_prompt()[:50] + "...")
    
    print("\n=== 格式化示例 ===")
    # 标题生成提示词格式化示例
    formatted_prompt = pm.get_title_generation_prompt().format(
        title_ref="视频原标题：测试视频\n",
        meta_desc="视频元数据：博主：张三，粉丝数：10万"
    )
    print("格式化后的标题提示词前100字符:", formatted_prompt[:100] + "...")
