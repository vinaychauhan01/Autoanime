import asyncio
import json
import os
import subprocess

from pathlib import Path


async def genss(file):
    process = subprocess.Popen(
        ["mediainfo", file, "--Output=JSON"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    stdout, _ = process.communicate()
    out = stdout.decode().strip()
    data = json.loads(out)
    duration = data["media"]["track"][0]["Duration"]
    return int(duration.split(".")[-2])


def convertTime(seconds):
    seconds = int(seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{sec:02}"


async def duration_s(file):
    tsec = await genss(file)
    x = round(tsec / 5)
    y = round(tsec / 5 + 30)
    pin = convertTime(x)
    pon = convertTime(y if y < tsec else tsec)
    return pin, pon


async def gen_ss_sam(hash_dir, filename, log):
    try:
        if not filename or not os.path.exists(filename):
            log.error("❌ Input file does not exist.")
            return "", ""

        os.makedirs(hash_dir, exist_ok=True)

        tsec = await genss(filename)
        fps = 10 / tsec

        # Generate 10 screenshots
        screenshot_cmd = f"ffmpeg -i '{filename}' -vf fps={fps} -vframes 10 '{hash_dir}/pic%01d.png'"
        process = await asyncio.create_subprocess_shell(
            screenshot_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        ss, dd = await duration_s(filename)
        out_sample = os.path.splitext(filename)[0] + "_sample.mkv"

        # Create sample video
        sample_cmd = (
            f'ffmpeg -i "{filename}" -preset ultrafast -ss {ss} -to {dd} '
            f'-c:v copy -crf 27 -map 0:v -c:a aac -map 0:a -c:s copy -map 0:s? "{out_sample}" -y'
        )
        process = await asyncio.create_subprocess_shell(
            sample_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await process.communicate()
        error_log = stderr.decode().strip()

        if not os.path.exists(out_sample) or os.path.getsize(out_sample) == 0:
            log.error("⚠️ Sample file not generated or is empty.")
            log.error(error_log)
            return "", ""

        return hash_dir, out_sample

    except Exception as err:
        log.error(f"🔥 gen_ss_sam failed: {err}")
        return "", ""