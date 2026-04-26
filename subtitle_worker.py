import os
import sys
import torch
from faster_whisper import WhisperModel

def format_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def main():
    if len(sys.argv) != 7:
        with open(sys.argv[6], 'w', encoding='utf-8') as f:
            f.write("ERROR: 参数数量错误")
        sys.exit(1)
    
    video_path = sys.argv[1]
    model_size = sys.argv[2]
    language = sys.argv[3] if sys.argv[3] != 'None' else None
    use_gpu = sys.argv[4].lower() == 'true'
    force_regenerate = sys.argv[5].lower() == 'true'
    output_queue_path = sys.argv[6]

    srt_path = video_path.rsplit('.', 1)[0] + ".srt"
    
    try:
        if not force_regenerate and os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
            with open(output_queue_path, 'w', encoding='utf-8') as f:
                f.write(srt_path)
            sys.exit(0)

        if use_gpu is None:
            use_gpu = torch.cuda.is_available()

        device = "cuda" if use_gpu else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        segments, _ = model.transcribe(video_path, language=language, beam_size=5)

        subtitle_lines = []
        for i, seg in enumerate(segments, start=1):
            start = format_time(seg.start)
            end = format_time(seg.end)
            subtitle_lines.append(f"{i}\n{start} --> {end}\n{seg.text}\n")

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(subtitle_lines))

        if not os.path.exists(srt_path) or os.path.getsize(srt_path) == 0:
            raise RuntimeError(f"字幕文件写入失败: {srt_path}")

        with open(output_queue_path, 'w', encoding='utf-8') as f:
            f.write(srt_path)
        
        sys.exit(0)
    except Exception as e:
        with open(output_queue_path, 'w', encoding='utf-8') as f:
            f.write(f"ERROR: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()