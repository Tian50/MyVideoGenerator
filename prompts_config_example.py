"""
提示词配置文件使用示例
这个文件展示了如何修改和使用 prompts_config.py 中的提示词
"""

from prompts_config import PromptManager

# ========== 示例1：查看所有提示词 ==========
def show_all_prompts():
    """显示所有可用的提示词"""
    print("=== 所有可用的提示词 ===")
    
    print("\n1. 翻译提示词:")
    print(PromptManager.get_translation_prompt("zh"))
    
    print("\n2. 修正提示词:")
    print(PromptManager.get_correction_prompt())
    
    print("\n3. 标题生成提示词:")
    print(PromptManager.get_title_generation_prompt())
    
    print("\n4. 博主信息提示词:")
    print(PromptManager.get_blogger_info_prompt())
    
    print("\n5. 高光检测提示词 (3个片段):")
    print(PromptManager.get_highlight_detection_prompt(3))
    
    print("\n6. 内容过滤提示词:")
    print(PromptManager.get_content_filter_prompt())
    
    print("\n7. 封面设计提示词:")
    print(PromptManager.get_cover_design_prompt())
    
    print("\n8. 标题分段提示词:")
    print(PromptManager.get_title_split_prompt())

# ========== 示例2：如何修改提示词 ==========
def how_to_modify_prompts():
    """展示如何修改提示词"""
    print("\n=== 如何修改提示词 ===")
    print("""
要修改提示词，请编辑 prompts_config.py 文件中的相应类。
例如，要修改标题生成提示词，可以：

1. 打开 prompts_config.py
2. 找到 TitleGeneratorPrompts 类
3. 修改 get_title_generation_prompt() 方法返回的字符串
4. 保存文件

修改示例：
```python
class TitleGeneratorPrompts:
    @staticmethod
    def get_title_generation_prompt():
        # 修改这里的提示词内容
        return '''{title_ref}{meta_desc}
下面的是视频字幕文本，请为这个视频起 **20 个**吸引人的标题...
（这里可以添加你的自定义要求）'''
```
""")

# ========== 示例3：使用提示词 ==========
def use_prompts_example():
    """展示如何在代码中使用提示词"""
    print("\n=== 使用提示词示例 ===")
    
    # 示例：使用翻译提示词
    print("1. 使用翻译提示词:")
    translation_prompt = PromptManager.get_translation_prompt("zh")
    print(f"提示词长度: {len(translation_prompt)} 字符")
    
    # 示例：使用标题生成提示词（带参数）
    print("\n2. 使用标题生成提示词（带参数）:")
    title_ref = "视频原标题：测试视频\n"
    meta_desc = "视频元数据：博主：张三，粉丝数：10万，发布日期：2024-01-01"
    title_prompt = PromptManager.get_title_generation_prompt().format(
        title_ref=title_ref, meta_desc=meta_desc
    )
    print(f"格式化后的提示词前100字符: {title_prompt[:100]}...")
    
    # 示例：使用博主信息提示词
    print("\n3. 使用博主信息提示词:")
    blogger_prompt = PromptManager.get_blogger_info_prompt().format(author_name="John Smith")
    print(f"格式化后的提示词: {blogger_prompt[:80]}...")

# ========== 示例4：自定义提示词 ==========
def create_custom_prompts():
    """展示如何创建自定义提示词类"""
    print("\n=== 创建自定义提示词 ===")
    print("""
如果你需要添加新的提示词，可以在 prompts_config.py 中添加新的类：

```python
class CustomPrompts:
    @staticmethod
    def get_custom_prompt(param1, param2):
        return f'''这是一个自定义提示词
参数1: {param1}
参数2: {param2}
请按要求完成任务...'''
```

然后在 PromptManager 中添加对应的方法：
```python
class PromptManager:
    @staticmethod
    def get_custom_prompt(param1, param2):
        return CustomPrompts.get_custom_prompt(param1, param2)
```
""")

# ========== 主程序 ==========
if __name__ == "__main__":
    print("提示词配置文件使用示例")
    print("=" * 50)
    
    show_all_prompts()
    how_to_modify_prompts()
    use_prompts_example()
    create_custom_prompts()
    
    print("\n" + "=" * 50)
    print("提示：所有提示词现在都集中在 prompts_config.py 文件中")
    print("修改提示词时只需编辑该文件，无需修改其他模块代码")