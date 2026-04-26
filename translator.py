import requests
import pysrt
import json
import re
import time
import os
from prompts_config import PromptManager

def _localize_translation(batch, translated_texts, api_key):
    """将翻译结果本地化为中国网络用语风格"""
    items = []
    for sub in batch:
        orig_text = sub.text
        trans_text = translated_texts[sub.index - 1]
        items.append(f"{sub.index}. 原文: {orig_text} -> 译文: {trans_text}")
    
    prompt = f"""请将以下翻译结果优化为更符合中国网络用语和口头表达习惯的版本:
    
翻译列表:
{chr(10).join(items)}

要求:
1. 使用中国人日常交流的幽默表达
2. 适当加入网络流行语
3. 保持专业内容的准确性
4. 返回格式必须为JSON数组，每个元素包含index和localized_text字段
5. 只优化确实需要本地化的部分，不要过度修改"""

    api_config = PromptManager.get_api_config("localization")
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": api_config.get("model", "deepseek-chat"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": api_config.get("temperature", 0.7),
        "max_tokens": api_config.get("max_tokens", 2000)
    }
    
    try:
        response = requests.post("https://api.deepseek.com/v1/chat/completions", 
                               json=payload, headers=headers, timeout=30)
        if response.status_code != 200:
            raise Exception(f"API 本地化失败: {response.text}")
        
        result = response.json()["choices"][0]["message"]["content"].strip()
        json_match = re.search(r'```json\s*(\[.*\])\s*```', result, re.DOTALL)
        if json_match:
            result = json_match.group(1)
        
        localized_list = json.loads(result)
        localized_dict = {}
        for item in localized_list:
            if "index" in item and "localized_text" in item:
                localized_dict[item["index"]] = item["localized_text"]
        
        # 应用本地化结果
        localized_texts = translated_texts.copy()
        for idx, text in localized_dict.items():
            localized_texts[idx - 1] = text
        
        return localized_texts
    except Exception as e:
        print(f"本地化 API 出错: {e}，将返回原始翻译")
        return translated_texts

def _get_corrections(original_batch, translated_dict, api_key, previous_corrections_text=""):
    """
    调用 API 检查翻译质量，并返回需要修正的条目列表。
    返回格式: [{"index": 序号, "correction": "正确的译文"}, ...]
    如果全部正确，返回空列表 []。
    previous_corrections_text: 上一轮已应用的修正记录（文本形式）
    """
    items = []
    for sub in original_batch:
        orig_text = sub.text
        trans_text = translated_dict.get(sub.index, "")
        items.append(f"{sub.index}. 原文: {orig_text} -> 译文: {trans_text}")
    
    # 添加上一轮修正信息
    history = ""
    if previous_corrections_text:
        history = f"\n\n上一轮已应用以下修正：\n{previous_corrections_text}\n请基于这些修正后的译文重新检查。"
    
    # 使用配置文件的提示词
    base_prompt = PromptManager.get_correction_prompt()
    prompt = base_prompt.format(history=history) + f"\n\n字幕列表：\n{chr(10).join(items)}"
    
    # 获取API配置
    api_config = PromptManager.get_api_config("correction")
    retry_config = PromptManager.get_retry_config()
    
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": api_config.get("model", "deepseek-chat"),
        "messages": [{"role": "user", "content": prompt}],
        "temperature": api_config.get("temperature", 0),
        "max_tokens": api_config.get("max_tokens", 1000)
    }
    try:
        response = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, headers=headers, timeout=retry_config.get("timeout", 30))
        if response.status_code != 200:
            raise Exception(f"API 校验失败: {response.text}")
        result = response.json()["choices"][0]["message"]["content"].strip()
        # 提取 JSON 数组
        json_match = re.search(r'\[.*\]', result, re.DOTALL)
        if json_match:
            corrections = json.loads(json_match.group())
            if isinstance(corrections, list):
                return corrections
        return []
    except Exception as e:
        print(f"校验 API 出错: {e}，将不进行修正")
        return []

def translate_subtitle(srt_path, api_key, target_lang="zh", max_chars=1000, force_regenerate=False):
    """
    使用 DeepSeek API 翻译字幕文件，支持长文本自动分段。
    每批翻译后调用校验 API 获取修正，最多进行3轮修正。
    每一轮会将上一轮修正内容传给校验 API。
    """
    translated_path = srt_path.replace(".srt", f"_{target_lang}.srt")
    
    print(f"########### 开始翻译 #################")
    if not force_regenerate and os.path.exists(translated_path) and os.path.getsize(translated_path) > 0:
        print(f"翻译文件已存在: {translated_path}，跳过翻译")
        return translated_path

    subs = pysrt.open(srt_path, encoding='utf-8')
    
    # 分批
    batches = []
    current_batch = []
    current_len = 0
    for sub in subs:
        text_len = len(sub.text)
        if current_len + text_len > max_chars and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_len = 0
        current_batch.append(sub)
        current_len += text_len
    if current_batch:
        batches.append(current_batch)

    total_batches = len(batches)
    print(f"字幕共 {len(subs)} 条，分为 {total_batches} 批翻译")
    
    translated_texts = [None] * len(subs)
    
    # 获取API配置
    api_config = PromptManager.get_api_config("translation")
    retry_config = PromptManager.get_retry_config()
    
    for batch_idx, batch in enumerate(batches, start=1):
        print(f"\n--- 正在翻译第 {batch_idx}/{total_batches} 批 (共 {len(batch)} 条字幕) ---")
        
        items = [{"index": sub.index, "text": sub.text} for sub in batch]
        # 使用配置文件的提示词
        prompt = PromptManager.get_translation_prompt(target_lang) + f"\n\n输入：\n{json.dumps(items, ensure_ascii=False)}"
        
        # 翻译重试
        max_retries = retry_config.get("max_retries", 3)
        success = False
        trans_dict = None
        
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": api_config.get("model", "deepseek-chat"),
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": api_config.get("temperature", 0.3),
                        "max_tokens": api_config.get("max_tokens", 2000)
                    },
                    timeout=retry_config.get("timeout", 60)
                )
                if response.status_code != 200:
                    raise Exception(f"API 返回错误: {response.status_code} - {response.text}")
                result = response.json()["choices"][0]["message"]["content"].strip()
                
                json_match = re.search(r'```json\s*(\[.*\])\s*```', result, re.DOTALL)
                if json_match:
                    result = json_match.group(1)
                else:
                    result = result.strip()
                translated_list = json.loads(result)
                trans_dict = {}
                for item in translated_list:
                    if "index" in item and "translation" in item:
                        trans_dict[item["index"]] = item["translation"]
                
                # 完整性检查
                missing = [sub.index for sub in batch if sub.index not in trans_dict]
                if missing:
                    print(f"警告：缺少序号 {missing} 的翻译，将用原文代替")
                    for idx in missing:
                        for sub in batch:
                            if sub.index == idx:
                                trans_dict[idx] = sub.text
                                break
                
                success = True
                break
            except Exception as e:
                print(f"✗ 第 {batch_idx} 批翻译失败 (尝试 {attempt+1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_config.get("backoff_factor", 2) ** attempt)
                else:
                    print(f"⚠️ 第 {batch_idx} 批经过 {max_retries} 次重试仍失败，将保留原文")
                    for sub in batch:
                        translated_texts[sub.index - 1] = sub.text
                    break
        
        if not success:
            continue
        
        # 多轮校验修正（最多3轮）
        max_correction_rounds = 2
        previous_corrections_text = ""
        for round_num in range(max_correction_rounds):
            corrections = _get_corrections(batch, trans_dict, api_key, previous_corrections_text)
            if not corrections:
                print(f"✓ 校验通过，无需修正")
                break
            else:
                print(f"校验发现 {len(corrections)} 处问题，正在进行第 {round_num+1} 轮修正...")
                # 记录本轮修正内容
                round_corrections = []
                for corr in corrections:
                    idx = corr.get("index")
                    new_text = corr.get("correction")
                    if idx and new_text:
                        trans_dict[idx] = new_text
                        round_corrections.append(f"序号 {idx} 修正为: {new_text}")
                        print(f"  修正序号 {idx}: {new_text[:50]}...")
                # 将本轮修正内容累积到历史文本中
                if round_corrections:
                    previous_corrections_text += "\n" + "\n".join(round_corrections)
        if round_num == max_correction_rounds - 1:
            print(f"已达到最大修正次数 ({max_correction_rounds})，停止修正")
        
        # 存储结果
        for sub in batch:
            translated_texts[sub.index - 1] = trans_dict.get(sub.index, sub.text)
        
        # 本地化优化
        if batch_idx == total_batches:  # 只在最后一批进行本地化优化
            print("正在进行本地化优化...")
            localized_texts = _localize_translation(batch, translated_texts, api_key)
            for i, text in enumerate(localized_texts):
                if text:
                    translated_texts[i] = text
        
        print(f"✓ 第 {batch_idx} 批翻译完成")
        
        percent = (batch_idx / total_batches) * 100
        print(f"总进度: {percent:.1f}% ({batch_idx}/{total_batches})")
    
    # 应用翻译结果
    for sub, new_text in zip(subs, translated_texts):
        if new_text is not None:
            sub.text = new_text
    
    subs.save(translated_path, encoding='utf-8')
    print(f"\n✅ 翻译完成，保存至 {translated_path}")
    return translated_path