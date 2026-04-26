import yt_dlp
import os
import re
import subprocess
import sys
from pathlib import Path

# 设置控制台编码为UTF-8，解决中文显示问题
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

def safe_filename(text: str) -> str:
    """
    将字符串转换为安全的文件名，移除 Windows 不允许的字符：
    \ / : * ? " < > | 以及 Emoji 等非文字符号
    """
    # 移除非法字符 \ / : * ? " < > |
    safe = re.sub(r'[\\/*?:"<>|]', '', text)
    # 移除 Emoji 和特殊符号（保留字母、数字、中文、空格、点、下划线、横线）
    safe = re.sub(r'[^\w\s\u4e00-\u9fff.-]', '', safe)
    safe = safe.strip().rstrip('.')
    if not safe:
        safe = "video"
    return safe

def download_video(url, output_path="./videos"):
    """
    下载 YouTube 视频及封面，并提取客观元数据（作者、发布日期、粉丝数、播放量、点赞数等）
    返回: (title, video_path, metadata_dict)
    """
    os.makedirs(output_path, exist_ok=True)
    
    print("🔍 正在获取视频信息...")
    
    # 先用一个临时 ydl 只获取信息（不下载），得到原始标题
    temp_opts = {
        'quiet': True,
        'ignoreerrors': True,  # 忽略错误
    }
    
    raw_title = "video"
    try:
        with yt_dlp.YoutubeDL(temp_opts) as ydl_temp:
            info = ydl_temp.extract_info(url, download=False)
            if info:
                raw_title = info.get('title', 'video')
                print(f"✅ 获取视频信息成功: {raw_title}")
            else:
                print("⚠️  无法获取视频信息，使用默认标题")
    except Exception as e:
        print(f"⚠️  获取视频信息失败: {e}")
        # 尝试更简单的方式
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl_temp:
                info = ydl_temp.extract_info(url, download=False)
                if info:
                    raw_title = info.get('title', 'video')
        except Exception as e2:
            print(f"❌ 获取视频信息失败: {e2}")
            raw_title = "video"
    
    # 生成安全的文件名
    safe_title = safe_filename(raw_title)
    

















        # 设置输出模板，使用安全标题
    # 使用原来的1080p格式设置，按优先级尝试
    format_strategies = [
        # 策略1: 1080p MP4 (原代码的设置)
        'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]',
        # 策略2: 1080p 任何格式
        'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        # 策略3: 720p
        'bestvideo[height<=720]+bestaudio/best[height<=720]',
        # 策略4: 任何质量
        'bestvideo+bestaudio/best',
        # 策略5: 最简单的
        'best',
    ]
    
    last_error = None
    for i, format_str in enumerate(format_strategies):
        print(f"\n🔄 尝试格式策略 {i+1}")
        
        ydl_opts = {
            'outtmpl': os.path.join(output_path, f"{safe_title}.%(ext)s"),
            'format': format_str,
            'merge_output_format': 'mp4',
            'writethumbnail': True,
            'quiet': True,
            'ignoreerrors': True,
            'no_warnings': True,
            'retries': 3,
            'fragment_retries': 3,
        }
        
        try:
            print(f"📥 开始下载: {safe_title} (格式: {format_str[:50]}...)")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 提取信息并下载
                info = ydl.extract_info(url, download=True)
                
                if not info:
                    last_error = "无法获取视频内容"
                    continue
                
                # 检查下载的文件
                video_ext = info.get('ext', 'mp4')
                video_path = os.path.join(output_path, f"{safe_title}.{video_ext}")
                
                # 如果文件不存在，尝试查找
                if not os.path.exists(video_path):
                    import glob
                    pattern = os.path.join(output_path, f"{safe_title}.*")
                    files = glob.glob(pattern)
                    if files:
                        # 找到最大的文件（通常是视频）
                        files.sort(key=os.path.getsize, reverse=True)
                        video_path = files[0]
                    else:
                        last_error = "未找到下载的文件"
                        continue
                
                # 检查文件大小
                file_size = os.path.getsize(video_path) if os.path.exists(video_path) else 0
                if file_size < 1024 * 100:  # 小于100KB
                    last_error = f"文件太小 ({file_size} bytes)"
                    try:
                        os.remove(video_path)
                    except:
                        pass
                    continue
                
                # 获取分辨率信息
                height = info.get('height', 0)
                width = info.get('width', 0)
                
                print(f"✅ 下载成功!")
                print(f"   文件: {video_path}")
                print(f"   大小: {file_size / 1024 / 1024:.2f} MB")
                print(f"   分辨率: {width}x{height}")
                
                # 提取客观元数据
                uploader = info.get('uploader', '未知')
                upload_date = info.get('upload_date', '')
                if len(upload_date) == 8:
                    upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}"
                
                subscriber_count = info.get('channel_follower_count') or 0
                if subscriber_count >= 10000:
                    subscribers_str = f"{subscriber_count/10000:.1f}万".rstrip('0').rstrip('.')
                else:
                    subscribers_str = str(subscriber_count) if subscriber_count > 0 else '未知'
                
                view_count = info.get('view_count', 0)
                like_count = info.get('like_count', 0)
                
                metadata = {
                    'author': uploader,
                    'upload_date': upload_date,
                    'subscribers': subscribers_str,
                    'view_count': view_count,
                    'like_count': like_count,
                    'video_title': safe_title,
                    'video_url': url,
                    'resolution': f"{width}x{height}",
                }
                
                # 下载封面
                thumbnail_url = info.get('thumbnail')
                cover_path = None
                if thumbnail_url:
                    import requests
                    cover_ext = thumbnail_url.split('.')[-1].split('?')[0]
                    if cover_ext not in ['jpg', 'jpeg', 'png']:
                        cover_ext = 'jpg'
                    cover_path = os.path.join(output_path, f"{safe_title}_cover.{cover_ext}")
                    try:
                        r = requests.get(thumbnail_url, timeout=10)
                        with open(cover_path, 'wb') as f:
                            f.write(r.content)
                        print(f"✅ 封面下载完成: {cover_path}")
                    except Exception as e:
                        print(f"⚠️ 封面下载失败: {e}")
                        cover_path = None
                
                return safe_title, video_path, metadata
                
        except Exception as e:
            last_error = str(e)
            print(f"❌ 策略 {i+1} 失败: {last_error[:100]}")
            continue
    
        # 所有策略都失败
    raise Exception(f"无法下载视频 {url}: {last_error}")