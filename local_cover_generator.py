import subprocess
import os
import json
import re
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import requests
from prompts_config import PromptManager

# ---------- 通用辅助函数 ----------
def extract_frame(video_path, timestamp_sec, output_path):
    cmd = [
        "ffmpeg", "-ss", str(timestamp_sec), "-i", video_path,
        "-vframes", "1", "-q:v", "2", "-y", output_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def time_str_to_seconds(t):
    if isinstance(t, (int, float)):
        return float(t)
    if isinstance(t, str):
        t = t.strip()
        if ':' in t:
            parts = t.split(':')
            if len(parts) == 3:
                h, m, s = parts
                return int(h)*3600 + int(m)*60 + float(s)
            elif len(parts) == 2:
                m, s = parts
                return int(m)*60 + float(s)
        else:
            return float(t)
    return 0.0

def get_start_point(timestamp_str):
    if not timestamp_str:
        return None
    if '-' in timestamp_str:
        start_str = timestamp_str.split('-')[0].strip()
        start_sec = time_str_to_seconds(start_str)
    else:
        start_sec = time_str_to_seconds(timestamp_str)
    return start_sec

def sanitize_filename(name):
    illegal_map = {
        '\\': '＼', '/': '／', ':': '：', '*': '＊', '?': '？',
        '"': '“', '<': '＜', '>': '＞', '|': '｜'
    }
    for illegal, fullwidth in illegal_map.items():
        name = name.replace(illegal, fullwidth)
    return name[:50]

# ---------- 裁剪中心区域与合成 ----------
def crop_center_region(image_path, output_path, crop_ratio=1/7):
    img = Image.open(image_path)
    w, h = img.size
    left_crop = int(w * crop_ratio)
    right_crop = w - left_crop
    top_crop = int(h * crop_ratio)
    bottom_crop = h - top_crop
    cropped = img.crop((left_crop, top_crop, right_crop, bottom_crop))
    cropped.save(output_path)
    return cropped.size

def combine_with_borders(original_path, center_path, output_path, crop_ratio=1/7):
    original = Image.open(original_path)
    center = Image.open(center_path)
    w, h = original.size
    left_crop = int(w * crop_ratio)
    right_crop = w - left_crop
    top_crop = int(h * crop_ratio)
    bottom_crop = h - top_crop

    target_w = right_crop - left_crop
    target_h = bottom_crop - top_crop
    if center.size != (target_w, target_h):
        center = center.resize((target_w, target_h), Image.Resampling.LANCZOS)

    result = Image.new('RGB', (w, h))
    result.paste(original.crop((0, 0, w, top_crop)), (0, 0))
    result.paste(original.crop((0, bottom_crop, w, h)), (0, bottom_crop))
    result.paste(original.crop((0, top_crop, left_crop, bottom_crop)), (0, top_crop))
    result.paste(original.crop((right_crop, top_crop, w, bottom_crop)), (right_crop, top_crop))
    result.paste(center, (left_crop, top_crop))
    result.save(output_path)

# ---------- DeepSeek 智能分段 ----------
def get_title_lines_from_deepseek(title_text, api_key, max_retries=2):
    # 使用配置文件的提示词
    prompt = PromptManager.get_title_split_prompt().format(title_text=title_text)
    for attempt in range(max_retries):
        try:
            response = requests.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 150
                },
                timeout=30
            )
            if response.status_code != 200:
                raise Exception(f"API 请求失败: {response.status_code}")
            content = response.json()["choices"][0]["message"]["content"].strip()
            json_match = re.search(r'\[.*\]', content, re.DOTALL)
            if json_match:
                lines = json.loads(json_match.group())
                if isinstance(lines, list) and all(isinstance(l, str) for l in lines):
                    return lines[:3]
            return fallback_split(title_text)
        except Exception as e:
            print(f"⚠️ DeepSeek 分段失败 (尝试 {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return fallback_split(title_text)
            time.sleep(2)
    return fallback_split(title_text)

def fallback_split(text, max_len=12):
    if len(text) <= max_len:
        return [text]
    for sep in ['，', '。', '！', '？', '；', '：', ',', '.', '!', '?']:
        if sep in text:
            parts = text.split(sep, 1)
            if len(parts[0]) <= max_len and len(parts[1]) <= max_len:
                return [parts[0], parts[1]]
            if len(parts[0]) <= max_len:
                return [parts[0], parts[1][:max_len]]
    return [text[:max_len], text[max_len:2*max_len]]

# ---------- 安全的字体加载函数 ----------
def load_font(font_path, size):
    """安全加载字体，失败时返回默认字体"""
    if font_path and os.path.exists(font_path):
        try:
            # 使用原始字符串路径，处理空格和中文字符
            return ImageFont.truetype(str(font_path), size)
        except Exception as e:
            print(f"⚠️ 无法加载字体文件 {font_path}: {e}")
    return ImageFont.load_default()

# ---------- 动态多行文字绘制 ----------
def draw_multiline_text_dynamic(
    image_path, lines, output_path, font_path=None, italic_font_path=None,
    position="bottom", margin=40,
    colors=None,
    max_font_size=150, min_font_size=24, horizontal_padding=20,
    stroke_width=6, stroke_color=(0,0,0),
    shadow_offset=3, shadow_color=(0,0,0,128),
    line_spacing_ratio=0.2
):
    img = Image.open(image_path).convert("RGBA")
    img_width, img_height = img.size
    draw = ImageDraw.Draw(img)

    if colors is None:
        if len(lines) == 2:
            colors = [(255,222,0), (183,220,246)]
        elif len(lines) == 3:
            colors = [(255,222,0), (183,220,246), (255,222,0)]
        else:
            colors = [(255,222,0)] * len(lines)

    available_width = img_width - 2 * horizontal_padding
    if available_width <= 0:
        available_width = img_width - 40

    # 确定使用的字体路径
    if italic_font_path and os.path.exists(italic_font_path):
        target_font_path = italic_font_path
        font_type = "斜体"
    elif font_path and os.path.exists(font_path):
        target_font_path = font_path
        font_type = "普通（未找到斜体字体）"
        print(f"⚠️ 未找到斜体字体文件，使用普通字体: {font_path}")
    else:
        target_font_path = None
        font_type = "默认"
        print("⚠️ 未找到任何字体文件，使用默认字体")

    def get_text_width(text, font_size):
        font = load_font(target_font_path, font_size)
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0]

    line_data = []
    for line, color in zip(lines, colors):
        char_count = len(line)
        if char_count == 0:
            continue
        ideal_size = int(available_width / char_count * 0.9)
        target_size = max(min_font_size, min(max_font_size, ideal_size))
        best_size = target_size
        while best_size >= min_font_size:
            if get_text_width(line, best_size) <= available_width:
                break
            best_size -= 1
        if best_size < target_size and best_size < max_font_size:
            while best_size < target_size:
                next_size = best_size + 1
                if get_text_width(line, next_size) <= available_width:
                    best_size = next_size
                else:
                    break
        final_font = load_font(target_font_path, best_size)
        text_width = get_text_width(line, best_size)
        bbox = draw.textbbox((0, 0), line, font=final_font)
        text_height = bbox[3] - bbox[1]
        line_data.append({
            'text': line,
            'color': color,
            'font': final_font,
            'width': text_width,
            'height': text_height,
            'size': best_size
        })
        print(f"  行: '{line}' 字号: {best_size} 宽度: {text_width}/{available_width}")

    if not line_data:
        print("⚠️ 没有有效的文字行，直接复制原图")
        img.save(output_path, "JPEG", quality=95)
        return

    total_height = 0
    for i, data in enumerate(line_data):
        total_height += data['height']
        if i < len(line_data) - 1:
            total_height += int(data['height'] * line_spacing_ratio)

    if position == "bottom":
        y_start = img_height - total_height - margin
    elif position == "top":
        y_start = margin
    else:
        y_start = (img_height - total_height) // 2

    txt_layer = Image.new('RGBA', img.size, (0,0,0,0))
    txt_draw = ImageDraw.Draw(txt_layer)

    current_y = y_start
    for data in line_data:
        x = (img_width - data['width']) // 2
        if shadow_offset > 0:
            txt_draw.text((x + shadow_offset, current_y + shadow_offset),
                          data['text'], fill=shadow_color, font=data['font'])
        if stroke_width > 0:
            for dx in range(-stroke_width, stroke_width+1):
                for dy in range(-stroke_width, stroke_width+1):
                    if dx == 0 and dy == 0:
                        continue
                    txt_draw.text((x + dx, current_y + dy),
                                  data['text'], fill=stroke_color, font=data['font'])
        txt_draw.text((x, current_y), data['text'], fill=data['color'], font=data['font'])
        current_y += data['height'] + int(data['height'] * line_spacing_ratio)

    img = Image.alpha_composite(img, txt_layer).convert("RGB")
    img.save(output_path, "JPEG", quality=95)
    print(f"✅ 封面生成 (动态顶满样式): {output_path}")

# ---------- 批量生成封面 ----------
def generate_covers_local(
    title_items, original_video_path, output_dir,
    deepseek_api_key, font_path=None, italic_font_path=None,
    crop_ratio=1/7,
    position="bottom", margin=40,
    colors=None,
    max_font_size=150, min_font_size=24, horizontal_padding=20,
    stroke_width=3, stroke_color=(0,0,0),
    shadow_offset=3, shadow_color=(0,0,0,128),
    line_spacing_ratio=0.2
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cover_paths = []

    screenshot_points = []
    for item in title_items:
        ts = item.get("timestamp")
        if not ts:
            continue
        sec = get_start_point(ts)
        if sec is None:
            continue
        screenshot_points.append((sec, item["title"]))

    for idx, (time_sec, title) in enumerate(screenshot_points):
        frame_path = output_dir / f"frame_{idx+1}.jpg"
        extract_frame(original_video_path, time_sec, str(frame_path))
        print(f"📸 截图 {idx+1}: {frame_path} (时间点 {time_sec:.2f}s)")

        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            center_path = tmp.name
        crop_center_region(str(frame_path), center_path, crop_ratio=crop_ratio)

        lines = get_title_lines_from_deepseek(title, deepseek_api_key)
        print(f"🤖 标题分段结果: {lines}")

        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_drawn:
            drawn_center_path = tmp_drawn.name
        draw_multiline_text_dynamic(
            center_path, lines, drawn_center_path,
            font_path=font_path,
            italic_font_path=italic_font_path,
            position=position,
            margin=margin,
            colors=colors,
            max_font_size=max_font_size,
            min_font_size=min_font_size,
            horizontal_padding=horizontal_padding,
            stroke_width=stroke_width,
            stroke_color=stroke_color,
            shadow_offset=shadow_offset,
            shadow_color=shadow_color,
            line_spacing_ratio=line_spacing_ratio
        )

        safe_title = sanitize_filename(title)
        cover_path = output_dir / f"{safe_title}.jpg"
        combine_with_borders(str(frame_path), drawn_center_path, str(cover_path), crop_ratio=crop_ratio)

        os.unlink(center_path)
        os.unlink(drawn_center_path)
        cover_paths.append(cover_path)

    return cover_paths