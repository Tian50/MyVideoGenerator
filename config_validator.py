"""
配置验证工具
用于验证 prompts_config.py 中的所有配置是否正确
"""

import sys
import os
sys.path.insert(0, '.')

from prompts_config import PromptManager, ConfigValidator

def validate_configs():
    """验证所有配置"""
    print("=" * 60)
    print("配置验证工具")
    print("=" * 60)
    
    # 验证配置
    errors = ConfigValidator.validate_all_configs()
    
    if errors:
        print("\n配置验证失败，发现以下错误：")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
        return False
    else:
        print("\n所有配置验证通过")
        return True

def show_api_configs():
    """显示所有API配置"""
    print("\n" + "=" * 60)
    print("API配置详情")
    print("=" * 60)
    
    task_types = [
        "translation",
        "correction", 
        "title_generation",
        "blogger_info",
        "highlight_detection",
        "content_filter",
        "title_split"
    ]
    
    for task_type in task_types:
        config = PromptManager.get_api_config(task_type)
        print(f"\n{task_type.upper()}:")
        print(f"  模型: {config.get('model', '未设置')}")
        print(f"  温度: {config.get('temperature', '未设置')}")
        print(f"  最大token数: {config.get('max_tokens', '未设置')}")

def show_retry_config():
    """显示重试配置"""
    print("\n" + "=" * 60)
    print("重试配置")
    print("=" * 60)
    
    retry_config = PromptManager.get_retry_config()
    print(f"最大重试次数: {retry_config.get('max_retries', '未设置')}")
    print(f"退避因子: {retry_config.get('backoff_factor', '未设置')}")
    print(f"超时时间: {retry_config.get('timeout', '未设置')}秒")

def test_prompts():
    """测试所有提示词"""
    print("\n" + "=" * 60)
    print("提示词测试")
    print("=" * 60)
    
    test_cases = [
        ("翻译提示词", lambda: PromptManager.get_translation_prompt("zh")),
        ("修正提示词", PromptManager.get_correction_prompt),
        ("标题生成提示词", PromptManager.get_title_generation_prompt),
        ("博主信息提示词", lambda: PromptManager.get_blogger_info_prompt().format(author_name="测试博主")),
        ("高光检测提示词", lambda: PromptManager.get_highlight_detection_prompt(3)),
        ("内容过滤提示词", PromptManager.get_content_filter_prompt),
        ("封面设计提示词", lambda: PromptManager.get_cover_design_prompt().format(title_text="测试标题")),
        ("标题分段提示词", lambda: PromptManager.get_title_split_prompt().format(title_text="测试标题")),
    ]
    
    for name, func in test_cases:
        try:
            result = func()
            if result and isinstance(result, str):
                print(f"{name}: 正常 (长度: {len(result)} 字符)")
                # 显示前50个字符
                preview = result[:50] + "..." if len(result) > 50 else result
                print(f"   预览: {preview}")
            else:
                print(f"{name}: 返回无效值")
        except Exception as e:
            print(f"{name}: 调用失败 - {e}")

def main():
    """主函数"""
    print("开始验证配置...")
    
    # 验证配置
    if not validate_configs():
        print("\n配置验证失败，请修复上述错误")
        return
    
    # 显示配置详情
    show_api_configs()
    show_retry_config()
    
    # 测试提示词
    test_prompts()
    
    print("\n" + "=" * 60)
    print("配置验证完成")
    print("=" * 60)
    
    # 提供修改建议
    print("\n修改提示：")
    print("1. 要修改API配置，请编辑 prompts_config.py 中的 APIConfig.DEEPSEEK_CONFIG")
    print("2. 要修改提示词，请编辑 prompts_config.py 中对应的 Prompts 类")
    print("3. 要修改重试配置，请编辑 prompts_config.py 中的 APIConfig.RETRY_CONFIG")
    print("\n所有配置现在都集中在 prompts_config.py 文件中，便于管理。")

if __name__ == "__main__":
    main()