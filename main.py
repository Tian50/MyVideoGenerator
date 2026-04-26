import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

from downloader import download_video
from subtitle_generator import generate_subtitle
from translator import translate_subtitle
from title_generator import generate_titles_from_srt
from embed_subtitle import embed_subtitles_auto
from highlight_detector import detect_highlight_timestamps_from_srt
from highlight_extractor import extract_highlights_clip, concat_videos
from metadata_overlay import add_metadata_to_video, add_metadata_to_start
from local_cover_generator import generate_covers_local
from blogger_info import get_blogger_info, merge_blogger_info_to_metadata
from content_filter import filter_content_by_srt
from video_classifier import classify_video, get_category_display_name
from type_specific_extractor import extract_type_specific_clips

load_dotenv()

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
VIDEO_OUTPUT_PATH = os.getenv("VIDEO_OUTPUT_PATH", "./videos")
CHINESE_FONT_PATH = os.getenv("CHINESE_FONT_PATH")


def process_video(video_url, no_subtitles=False, no_highlight=True, no_metadata=True, no_title_cover=False, originsub=False, cnmargin=220):
    try:
        title, video_path, metadata = download_video(video_url, output_path=VIDEO_OUTPUT_PATH)
        print(f"✅ 下载完成: {title}")

        # ========== 视频来源类型分类（初次：仅用标题+作者） ==========
        print("🔍 正在分析视频来源类型...")
        author_info = metadata.get('author', '')
        classification_result = classify_video(
            author_info=author_info,
            subtitle_sample="",
            original_title=title,
            api_key=DEEPSEEK_API_KEY
        )
        if classification_result.get("status") == "success":
            video_category = classification_result["category"]
            print(f"📺 视频来源类型: {get_category_display_name(video_category)} (理由: {classification_result['reason']})")
            metadata["video_category"] = video_category
        else:
            print(f"⚠️ 视频来源类型分析失败: {classification_result.get('error', '未知错误')}")
            metadata["video_category"] = ""
        # ==========================================================

        # 查询博主信息
        if not no_title_cover:
            print("🔍 正在查询博主个人信息...")
            blogger_info = get_blogger_info(metadata, DEEPSEEK_API_KEY)
            if blogger_info.get("status") == "success":
                print(f"📝 博主信息: 国籍={blogger_info.get('nationality')}, 性别={blogger_info.get('gender')}, 外号={blogger_info.get('chinese_nickname')}")
                metadata = merge_blogger_info_to_metadata(metadata, blogger_info)
            else:
                print(f"⚠️ 博主信息查询失败: {blogger_info.get('error', '未知错误')}")

        # 准备元数据
        video_metadata = {
            'author': metadata.get('author', ''),
            'upload_date': metadata.get('upload_date', ''),
            'subscribers': metadata.get('subscribers', ''),
            'view_count': metadata.get('view_count', 0),
            'like_count': metadata.get('like_count', 0),
            'blogger_nationality': metadata.get('blogger_nationality', ''),
            'blogger_gender': metadata.get('blogger_gender', ''),
            'blogger_nickname': metadata.get('blogger_nickname', '')
        }
        print(f"📝 完整视频元数据: {video_metadata}")

        # 生成字幕
        original_srt = generate_subtitle(video_path)
        print(f"📝 英文字幕生成: {original_srt}")
        chinese_srt = translate_subtitle(original_srt, api_key=DEEPSEEK_API_KEY)
        print(f"🌐 中文字幕翻译完成: {chinese_srt}")

        # ========== 用字幕内容再次进行视频分类（更精确） ==========
        try:
            with open(original_srt, "r", encoding="utf-8") as f:
                subtitle_content = f.read()[:2000]
            refined_result = classify_video(
                author_info=metadata.get('author', ''),
                subtitle_sample=subtitle_content,
                original_title=title,
                api_key=DEEPSEEK_API_KEY
            )
            if refined_result.get("status") == "success":
                video_category = refined_result["category"]
                print(f"📺 视频来源类型(精判): {get_category_display_name(video_category)} (理由: {refined_result['reason']})")
                metadata["video_category"] = video_category
        except Exception as e:
            print(f"⚠️ 视频来源类型精细分析失败: {e}")
        # ========================================================

        # 生成标题建议
        title_suggestions = None
        if not no_title_cover:
            title_suggestions = generate_titles_from_srt(chinese_srt, DEEPSEEK_API_KEY, video_metadata=video_metadata, original_title=title)
            print("\n--- 候选标题建议 ---")
            if title_suggestions:
                for idx, item in enumerate(title_suggestions, 1):
                    timestamp_info = f" (时间: {item['timestamp']})" if item.get('timestamp') else ""
                    print(f"{idx}. {item['title']}{timestamp_info}")
                auto_title = title_suggestions[0]['title']
            else:
                print("生成标题失败，使用原始标题")
                auto_title = title[:20]
            print(f"\n🎯 自动选用标题: {auto_title}")

        # 输出目录
        output_dir = Path("./output") / Path(title).stem
        output_dir.mkdir(parents=True, exist_ok=True)

        # 嵌入字幕（硬编码，输出 MP4）
        video_with_subs = video_path
        if not no_subtitles:
            embedded_video = output_dir / f"{Path(video_path).stem}_with_subs.mp4"
            if embedded_video.exists():
                print(f"⏭️ 字幕文件已存在: {embedded_video}")
                video_with_subs = str(embedded_video)
            else:
                video_with_subs = embed_subtitles_auto(
                    video_path=video_path,
                    srt_base_path=original_srt if not args.originsub else chinese_srt,
                    output_path=str(embedded_video),
                    font_path=CHINESE_FONT_PATH,
                    cn_margin=args.cnmargin,
                    en_margin=20,
                    encoder="h264_nvenc",
                    include_original=False
                )
                print(f"🎬 字幕已嵌入: {video_with_subs}")
        else:
            print("⏭️ 跳过字幕嵌入（--nosubtitles）")

        # 高光检测与独立片头生成
        highlights_clip_path = None
        if not no_highlight:
            highlight_timestamps = detect_highlight_timestamps_from_srt(original_srt, DEEPSEEK_API_KEY, num=3)
            if highlight_timestamps:
                highlights_clip_path = output_dir / f"{Path(video_with_subs).stem}_highlights_clip.mp4"
                if highlights_clip_path.exists():
                    print(f"⏭️ 高光片头已存在: {highlights_clip_path}")
                else:
                    extract_highlights_clip(
                        original_video_path=video_with_subs,
                        segments=highlight_timestamps,
                        output_path=str(highlights_clip_path),
                        use_gpu=True
                    )
                print(f"✨ 高光片头已生成: {highlights_clip_path}")
            else:
                print("⏭️ 未检测到有效高光片段")
        else:
            print("⏭️ 跳过高光检测（--nohighlight）")

        # 违规内容切除
        video_censored = output_dir / f"{Path(video_with_subs).stem}_censored.mp4"
        if video_censored.exists():
            print(f"⏭️ 已切除违规内容的视频已存在: {video_censored}")
        else:
            filter_content_by_srt(
                video_path=video_with_subs,
                srt_path=chinese_srt,
                api_key=DEEPSEEK_API_KEY,
                output_path=str(video_censored)
            )
        print(f"🎬 违规内容切除后视频: {video_censored}")

        # ========== 根据视频类型进行特定内容剪辑 ==========
        if metadata.get("video_category") in ["interview", "political"]:
            print(f"🔍 检测到{get_category_display_name(metadata['video_category'])}视频，开始提取特定片段...")
            type_specific_clip = output_dir / f"{Path(video_censored).stem}_type_specific.mp4"
            if type_specific_clip.exists():
                print(f"⏭️ 已提取的特定片段视频已存在: {type_specific_clip}")
                video_censored = str(type_specific_clip)
            else:
                extract_type_specific_clips(
                    video_path=str(video_censored),
                    srt_path=chinese_srt,
                    api_key=DEEPSEEK_API_KEY,
                    output_path=str(type_specific_clip),
                    video_category=metadata["video_category"]
                )
                video_censored = str(type_specific_clip)
                print(f"✨ 已提取特定片段视频: {video_censored}")

        # ========== 元数据处理：优先对高光片头叠加元数据，再拼接 ==========
        final_video_path = None

        if highlights_clip_path and highlights_clip_path.exists():
            if not no_metadata:
                highlights_with_meta = output_dir / f"{Path(highlights_clip_path).stem}_with_metadata.mp4"
                if highlights_with_meta.exists():
                    print(f"⏭️ 已添加元数据的高光片头已存在: {highlights_with_meta}")
                    highlights_to_use = str(highlights_with_meta)
                else:
                    highlights_to_use = add_metadata_to_video(
                        video_path=str(highlights_clip_path),
                        metadata=metadata,
                        output_path=str(highlights_with_meta),
                        font_path=CHINESE_FONT_PATH,
                        use_gpu=True,
                        duration=8
                    )
                    print(f"📝 元数据已添加至高光片头: {highlights_to_use}")
            else:
                highlights_to_use = str(highlights_clip_path)
                print("⏭️ 跳过添加元数据（--no-metadata）")

            video_with_highlights = output_dir / f"{Path(video_censored).stem}_with_highlights.mp4"
            if video_with_highlights.exists():
                print(f"⏭️ 已拼接高光片头的视频已存在: {video_with_highlights}")
                final_video_path = str(video_with_highlights)
            else:
                final_video_path = concat_videos(
                    [highlights_to_use, str(video_censored)],
                    str(video_with_highlights),
                    use_gpu=True
                )
                print(f"✨ 高光片头（已带元数据）已添加到开头: {final_video_path}")

        else:
            if not no_metadata:
                final_with_metadata = output_dir / f"{Path(video_censored).stem}_with_metadata.mp4"
                if final_with_metadata.exists():
                    print(f"⏭️ 元数据视频已存在: {final_with_metadata}")
                    final_video_path = str(final_with_metadata)
                else:
                    final_video_path = add_metadata_to_start(
                        video_path=str(video_censored),
                        metadata=metadata,
                        output_path=str(final_with_metadata),
                        font_path=CHINESE_FONT_PATH,
                        use_gpu=True,
                        duration=8
                    )
                    print(f"📝 元数据已添加至视频开头（切割方式）: {final_video_path}")
            else:
                final_video_path = str(video_censored)
                print("⏭️ 跳过添加元数据（--no-metadata）")

        # ========== 封面生成 ==========
        if not no_title_cover and title_suggestions:
            cover_dir = output_dir / "covers"
            try:
                italic_font_path = r"C:\Users\刘晓天\AppData\Local\Microsoft\Windows\Fonts\江城斜黑体 500W.ttf"
                if not os.path.exists(italic_font_path):
                    italic_font_path = r"C:\Windows\Fonts\江城斜黑体 500W.ttf"
                if not os.path.exists(italic_font_path):
                    print("⚠️ 斜体字体文件不存在，将使用普通字体")
                    italic_font_path = None

                cover_paths = generate_covers_local(
                    title_items=title_suggestions,
                    original_video_path=video_path,
                    output_dir=cover_dir,
                    deepseek_api_key=DEEPSEEK_API_KEY,
                    font_path=CHINESE_FONT_PATH,
                    italic_font_path=italic_font_path,
                    position="bottom",
                    margin=50,
                    max_font_size=200,
                    min_font_size=30,
                    horizontal_padding=30,
                    stroke_width=10,
                    stroke_color=(0, 0, 0),
                    line_spacing_ratio=0.2
                )
                print(f"\n🖼️ 已生成 {len(cover_paths)} 个本地封面，位于: {cover_dir}")
                for cp in cover_paths:
                    print(f"   {cp}")
            except Exception as e:
                print(f"❌ 本地封面生成失败: {e}")

        print(f"\n🎉 视频处理完成，最终输出: {final_video_path}")

    except Exception as e:
        print(f"❌ 处理视频 {video_url} 时出错: {e}")
        import traceback
        traceback.print_exc()


def main():
    parser = argparse.ArgumentParser(description="老外逛吃中国 - 全自动视频处理")
    parser.add_argument("urls", nargs="+", help="一个或多个视频URL")
    parser.add_argument("--nosubtitles", action="store_true", help="不将字幕嵌入视频")
    parser.add_argument("--nohighlight", action="store_true", help="不提取高光片段")
    parser.add_argument("--no-metadata", action="store_true", help="不添加视频元数据")
    parser.add_argument("--no-title-cover", action="store_true", help="不生成标题和封面")
    parser.add_argument("--originsub", action="store_true", help="使用原始字幕而非翻译字幕")
    parser.add_argument("--cnmargin", type=int, default=220, help="中文字幕边距")
    args = parser.parse_args()

    if not DEEPSEEK_API_KEY:
        raise ValueError("请在 .env 文件中设置 DEEPSEEK_API_KEY")

    for url in args.urls:
        process_video(
            url,
            no_subtitles=args.nosubtitles,
            no_highlight=args.nohighlight,
            no_metadata=args.no_metadata,
            no_title_cover=args.no_title_cover,
            originsub=args.originsub,
            cnmargin=args.cnmargin
        )


if __name__ == "__main__":
    main()
