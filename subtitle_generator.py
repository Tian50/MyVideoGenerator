import os
import sys
import tempfile
import subprocess
import torch

def generate_subtitle(video_path, model_size="large-v3", language=None, use_gpu=None, force_regenerate=False, timeout=3600):
    srt_path = video_path.rsplit('.', 1)[0] + ".srt"
    
    # 如果强制重新生成，先删除旧文件
    if force_regenerate and os.path.exists(srt_path):
        os.remove(srt_path)
    
    # 如果文件已存在且非空，直接返回
    if os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
        print(f"[subtitle_generator] 字幕已存在: {srt_path}", flush=True)
        return srt_path
    
    # 创建临时文件用于接收子进程输出
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as tmp:
        result_file = tmp.name
    
    if use_gpu is None:
        use_gpu_val = torch.cuda.is_available()
    else:
        use_gpu_val = use_gpu
    
    cmd = [
        sys.executable,
        "subtitle_worker.py",
        video_path,
        model_size,
        str(language) if language is not None else "None",
        str(use_gpu_val),
        str(force_regenerate),
        result_file
    ]
    
    print(f"[subtitle_generator] 启动子进程: {' '.join(cmd)}", flush=True)
    
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    
    try:
        proc = subprocess.run(cmd, timeout=timeout, capture_output=True, text=True, encoding='utf-8', env=env)
        if proc.returncode != 0:
            # 子进程异常退出，但可能已经生成了部分字幕文件？检查文件是否存在
            if os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
                print(f"[subtitle_generator] 子进程异常退出，但字幕文件已存在，继续使用: {srt_path}", flush=True)
                return srt_path
            else:
                # 读取错误信息
                if os.path.exists(result_file):
                    with open(result_file, 'r', encoding='utf-8') as f:
                        error_msg = f.read().strip()
                    if error_msg.startswith("ERROR:"):
                        raise Exception(error_msg[6:])
                raise Exception(f"子进程异常退出，返回码 {proc.returncode}\nSTDERR: {proc.stderr}")
        
        # 子进程正常退出，读取结果
        with open(result_file, 'r', encoding='utf-8') as f:
            srt_path = f.read().strip()
        if srt_path.startswith("ERROR:"):
            raise Exception(srt_path[6:])
        if not os.path.exists(srt_path) or os.path.getsize(srt_path) == 0:
            raise FileNotFoundError(f"字幕文件不存在或为空: {srt_path}")
        
        print(f"[subtitle_generator] 子进程完成，字幕文件: {srt_path}", flush=True)
        return srt_path
        
    except subprocess.TimeoutExpired:
        proc.kill()
        raise TimeoutError(f"字幕生成超时 ({timeout}秒)")
    except Exception as e:
        # 再次检查文件是否存在
        if os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
            print(f"[subtitle_generator] 发生异常但字幕文件已存在，继续使用: {srt_path}", flush=True)
            return srt_path
        raise
    finally:
        if os.path.exists(result_file):
            os.unlink(result_file)