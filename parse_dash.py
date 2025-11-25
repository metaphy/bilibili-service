"""
parse_dash.py

Pragmatic helper to process a Bilibili-style `dash` object in Python.

Usage (example):
    from parse_dash import parse_dash
    parse_dash(dash, 'BV1xxxxx')

This script implements a "fast path" used by many Bilibili responses:
- Video and audio representations contain a `baseUrl` pointing to a downloadable
  media file (often .mp4 or .m4s fragments). The script downloads the two
  files and uses `ffmpeg` to mux them into a final MP4.

It also supports a simple `SegmentList` style where each segment entry has a
`baseUrl` or similar. For more complex SegmentBase / byte-range index parsing
or full MPD support, use a dedicated DASH library or `ffmpeg` with a real MPD.

Dependencies:
- Python packages: `requests`, `tqdm` (optional for progress)
- System: `ffmpeg` available on PATH

"""
import os

import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional

import requests
from tqdm import tqdm


def _download(url: str, dst_path: str, session: Optional[requests.Session] = None) -> None:
    """Download a URL to dst_path with streaming and a progress bar."""
    s = session or requests.Session()
    resp = s.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    total = int(resp.headers.get("content-length", 0))
    with open(dst_path, "wb") as f:
        if total:
            for chunk in tqdm(resp.iter_content(chunk_size=8192), total=total // 8192, unit="KB"):
                if chunk:
                    f.write(chunk)
        else:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)


def _select_best(rep_list: List[Dict]) -> Dict:
    """Pick the 'best' representation from a list: prefer highest bandwidth."""
    if not rep_list:
        raise ValueError("No representations available")
    # Many APIs include 'bandwidth' — choose largest if present
    rep_with_bw = [r for r in rep_list if r.get("bandwidth") is not None]
    if rep_with_bw:
        return max(rep_with_bw, key=lambda r: int(r.get("bandwidth", 0)))
    # Fallback: return first
    return rep_list[0]


def _rep_to_urls(rep: Dict) -> List[str]:
    """Return a list of segment URLs for a representation.

    Supports common fields found in Bilibili JSON:
    - `baseUrl` (single URL, often the fast path)
    - `SegmentList` -> `SegmentURL` entries with `media` or `url` or `baseUrl`
    - `segments` or `segment` arrays with `baseUrl` or `url`
    """
    urls = []
    if not rep:
        return urls

    # Fast single-file URL
    if rep.get("baseUrl"):
        urls.append(rep.get("baseUrl"))
        return urls

    # Common alternative names
    seglist = rep.get("SegmentList") or rep.get("segmentList") or rep.get("segments") or rep.get("segment")
    if seglist:
        # SegmentList might be an object containing SegmentURL array
        if isinstance(seglist, dict):
            candidates = seglist.get("SegmentURL") or seglist.get("segmentURL") or seglist.get("segments")
        else:
            candidates = seglist
        if candidates:
            for s in candidates:
                if isinstance(s, dict):
                    url = s.get("media") or s.get("url") or s.get("baseUrl")
                    if url:
                        urls.append(url)
                elif isinstance(s, str):
                    urls.append(s)
    # Fallback: maybe there is a list of 'baseUrls'
    if not urls and rep.get("baseUrls"):
        for e in rep.get("baseUrls"):
            if isinstance(e, dict) and e.get("baseUrl"):
                urls.append(e.get("baseUrl"))
            elif isinstance(e, str):
                urls.append(e)

    return urls


def parse_dash(dash: Dict, bvid: str, out_dir: str = "public", output_name: Optional[str] = None) -> str:
    """Download and produce a muxed MP4 from a Bilibili `dash` dict.

    Returns the absolute path to the produced MP4.

    Behavior:
    - Choose the best video/audio rep (highest bandwidth if present)
    - If both video and audio have single `baseUrl`, download both and mux with ffmpeg
    - If reps provide a list of segments, download segments to temp files and try to concat/mux

    Note: This function aims to cover the typical "fast path" responses. For
    full DASH/MPD support, generate an MPD and let `ffmpeg` ingest it, or use
    a DASH library.
    """
    if not dash:
        raise ValueError("Empty dash object")

    os.makedirs(out_dir, exist_ok=True)
    output_name = output_name or f"{bvid}_new.mp4"
    output_path = os.path.abspath(os.path.join(out_dir, output_name))

    video_reps = dash.get("video") or dash.get("videos")
    audio_reps = dash.get("audio") or dash.get("audios")

    # defensive: dash might give top-level arrays
    if not video_reps and dash.get("videos"):
        video_reps = dash.get("videos")
    if not audio_reps and dash.get("audios"):
        audio_reps = dash.get("audios")

    if not video_reps or not audio_reps:
        raise ValueError("Dash object missing video or audio arrays")

    video = _select_best(video_reps)
    audio = _select_best(audio_reps)

    video_urls = _rep_to_urls(video)
    audio_urls = _rep_to_urls(audio)

    tmpdir = tempfile.mkdtemp(prefix=f"parse_dash_{bvid}_")

    session = requests.Session()
    try:
        # Fast path: both have single baseUrl
        if len(video_urls) == 1 and len(audio_urls) == 1:
            video_file = os.path.join(tmpdir, "video.mp4")
            audio_file = os.path.join(tmpdir, "audio.m4a")
            print(f"Downloading video -> {video_file}")
            _download(video_urls[0], video_file, session)
            print(f"Downloading audio -> {audio_file}")
            _download(audio_urls[0], audio_file, session)

            # Mux with ffmpeg
            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                video_file,
                "-i",
                audio_file,
                "-c",
                "copy",
                output_path,
            ]
            print("Muxing with ffmpeg:", " ".join(cmd))
            subprocess.check_call(cmd)
            return output_path

        # Fallback for multiple segments: download each list into one file and try to concat/mux
        def _download_join(urls: List[str], out_name: str) -> str:
            parts = []
            for i, u in enumerate(urls):
                part = os.path.join(tmpdir, f"{out_name}_part{i:03d}")
                print(f"Downloading segment {i+1}/{len(urls)} -> {part}")
                _download(u, part, session)
                parts.append(part)
            # Try to concatenate using ffmpeg concat demuxer by creating list file
            listfile = os.path.join(tmpdir, f"{out_name}_list.txt")
            with open(listfile, "w") as lf:
                for p in parts:
                    lf.write(f"file '{p}'\n")
            joined = os.path.join(tmpdir, f"{out_name}_joined.mp4")
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", joined]
            try:
                subprocess.check_call(cmd)
                return joined
            except subprocess.CalledProcessError:
                # If concat fails, as a last resort produce a raw dumped file pointing to the first segment
                return parts[0]

        vfile = _download_join(video_urls, "video") if video_urls else None
        afile = _download_join(audio_urls, "audio") if audio_urls else None

        if vfile and afile:
            cmd = ["ffmpeg", "-y", "-i", vfile, "-i", afile, "-c", "copy", output_path]
            subprocess.check_call(cmd)
            return output_path
        elif vfile:
            shutil.move(vfile, output_path)
            return output_path
        else:
            raise RuntimeError("Could not assemble media files from dash object")

    finally:
        # Cleanup tempdir
        try:
            shutil.rmtree(tmpdir)
        except Exception:
            pass


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 3:
        print("Usage: python parse_dash.py <dash-json-file> <bvid> [out_dir]")
        sys.exit(2)

    dash_json = sys.argv[1]
    bvid = sys.argv[2]
    out_dir = sys.argv[3] if len(sys.argv) > 3 else "public"

    with open(dash_json, "r") as f:
        dash_obj = json.load(f)

    out = parse_dash(dash_obj, bvid, out_dir)
    print("Wrote:", out)
