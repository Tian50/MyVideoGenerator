import subprocess
import base64
import requests
import os
import time
import json
import re
import tempfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import tos
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
    """从时间戳中提取开始时间（支持区间或单点），直接返回秒数"""
    if not timestamp_str:
        return None
    if '-' in timestamp_str:
        start_str = timestamp_str.split('-')[0].strip()
        start_sec = time_str_to_seconds(start_str)
    else:
        start_sec = time_str_to_seconds(timestamp_str)
    return start_sec

def sanitize_filename(name):
    """将Windows文件名中不允许的字符转换为全角等价字符"""
    illegal_map = {
        '\\': '＼',
        '/': '／',
        ':': '：',
        '*': '＊',
        '?': '？',
        '"': '“',
        '<': '＜',
        '>': '＞',
        '|': '｜'
    }
    for illegal, fullwidth in illegal_map.items():
        name = name.replace(illegal, fullwidth)
    return name[:50]

# ---------- TOS 上传 ----------
def upload_to_tos(image_path, bucket, endpoint, access_key, secret_key, region):
    client = tos.TosClientV2(access_key, secret_key, endpoint, region)
    object_key = f"covers/{Path(image_path).name}"
    client.upload_file(bucket, object_key, image_path)
    presigned_url = client.generate_presigned_url(
        Method='GET',
        Bucket=bucket,
        Key=object_key,
        ExpiresIn=3600
    )
    return presigned_url

# ---------- 裁剪中心区域（四边各裁 1/7） ----------
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
    # 上边框
    top_border = original.crop((0, 0, w, top_crop))
    result.paste(top_border, (0, 0))
    # 下边框
    bottom_border = original.crop((0, bottom_crop, w, h))
    result.paste(bottom_border, (0, bottom_crop))
    # 左边框（中间部分）
    left_border = original.crop((0, top_crop, left_crop, bottom_crop))
    result.paste(left_border, (0, top_crop))
    # 右边框
    right_border = original.crop((right_crop, top_crop, w, bottom_crop))
    result.paste(right_border, (right_crop, top_crop))
    # 中间核心区
    result.paste(center, (left_crop, top_crop))
    result.save(output_path)
    print(f"✅ 合成封面完成: {output_path}")

# ---------- 火山引擎即梦4.0 API（带裁剪合成） ----------
def generate_cover_with_jimeng4(original_image_path, title_text, output_path, api_config, **kwargs):
    from volcengine.visual.VisualService import VisualService

    access_key = api_config.get("access_key")
    secret_key = api_config.get("secret_key")
    if not access_key or not secret_key:
        raise ValueError("缺少火山引擎 Access Key 或 Secret Key")

    tos_bucket = api_config.get("tos_bucket")
    tos_endpoint = api_config.get("tos_endpoint")
    tos_region = api_config.get("tos_region")

    if not tos_bucket or not tos_endpoint:
        raise RuntimeError("未配置 TOS 存储桶信息，请设置 TOS_BUCKET 和 TOS_ENDPOINT")

    # 1. 裁剪原始图片，得到中心区域（四周各裁 1/7）
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
        center_path = tmp.name
    crop_center_region(original_image_path, center_path, crop_ratio=1/7)
    print(f"✂️ 已裁剪中心区域: {center_path}")

    # 2. 上传裁剪后的图片到 TOS
    print("📤 上传裁剪图到 TOS...")
    image_url = upload_to_tos(center_path, tos_bucket, tos_endpoint,
                              access_key, secret_key, tos_region)
    print(f"   图片 URL: {image_url}")

        # 3. 构造提示词（使用配置文件）
    prompt = PromptManager.get_cover_design_prompt().format(title_text=title_text)

    # 4. 提交任务（异步）
    service = VisualService()
    service.set_ak(access_key)
    service.set_sk(secret_key)
    service.set_host("visual.volcengineapi.com")

    req_body = {
        "req_key": "jimeng_t2i_v40",
        "image_urls": [image_url],
        "prompt": prompt,
        "scale": 0.5,
        "force_single": True,
        "size": 2048 * 1152   # 2K 横版面积
    }

    resp = service.common_json_handler("CVSync2AsyncSubmitTask", req_body)
    if resp.get("code") != 10000:
        raise Exception(f"提交任务失败: {resp}")

    task_id = resp["data"]["task_id"]
    print(f"📤 任务已提交，ID: {task_id}")

    # 5. 轮询结果
    for attempt in range(30):
        time.sleep(2)
        query_resp = service.common_json_handler("CVSync2AsyncGetResult", {
            "req_key": "jimeng_t2i_v40",
            "task_id": task_id,
            "req_json": json.dumps({"return_url": True})
        })
        if query_resp.get("code") != 10000:
            continue

        data = query_resp.get("data", {})
        status = data.get("status")
        if status == "done":
            img_url = data.get("image_urls", [None])[0]
            if img_url:
                # 下载生成的图片
                img_data = requests.get(img_url, timeout=30).content
                with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_gen:
                    gen_path = tmp_gen.name
                with open(gen_path, "wb") as f:
                    f.write(img_data)
                print(f"✅ 中间图片生成成功: {gen_path}")

                # 6. 将生成的中间图片与原始边框合并
                combine_with_borders(original_image_path, gen_path, output_path, crop_ratio=1/7)

                # 清理临时文件
                os.unlink(center_path)
                os.unlink(gen_path)
                return
            else:
                raise Exception("任务完成但未返回图片 URL")
        elif status in ("in_queue", "generating"):
            print(f"⏳ 生成中... ({attempt+1}/30)")
            continue
        else:
            raise Exception(f"任务状态异常: {status}")

    raise TimeoutError("轮询超时，任务未完成")

# ---------- 统一入口 ----------
def generate_cover_with_api(original_image_path, title_text, output_path, api_config, **kwargs):
    generate_cover_with_jimeng4(original_image_path, title_text, output_path, api_config, **kwargs)

# ---------- 批量生成封面 ----------
def generate_covers(title_items, original_video_path, output_dir,
                    img2img_config, multimodal_config=None, font_path=None):
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

        safe_title = sanitize_filename(title)
        cover_path = output_dir / f"{safe_title}.jpg"
        generate_cover_with_api(str(frame_path), title, str(cover_path), img2img_config, font_path=font_path)
        cover_paths.append(cover_path)

    return cover_paths