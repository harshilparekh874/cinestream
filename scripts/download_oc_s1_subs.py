"""Download The O.C. season 1 English subtitles from tvsubtitles.net and convert to VTT."""
import json
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

BASE = "https://www.tvsubtitles.net"
SEASON_URL = f"{BASE}/tvshow-21-1.html"
OUT_DIR = Path(__file__).resolve().parent.parent / "subtitles" / "the-oc"
TMP_DIR = Path(__file__).resolve().parent.parent / "_subs_tmp"


def fetch(url: str) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=120) as r:
        return r.read()


def parse_episodes(html: str):
    rows = re.findall(
        r"<td>1x(\d+)</td>.*?<td><nobr>(.*?)</nobr></td>",
        html,
        flags=re.DOTALL,
    )
    episodes = []
    for ep_num, nobr in rows:
        if ep_num == "All":
            continue
        m = re.search(
            r'href="subtitle-(\d+)\.html"[^>]*>\s*<img[^>]+alt="en"',
            nobr,
        )
        if not m:
            ep_page = re.search(
                r'href="(episode-\d+-en\.html)"[^>]*>\s*<img[^>]+alt="en"',
                nobr,
            )
            if ep_page:
                ep_html = fetch(f"{BASE}/{ep_page.group(1)}")
                m = re.search(r'href="/subtitle-(\d+)\.html"', ep_html)
        if not m:
            print(f"  skip 1x{ep_num}: no EN link")
            continue
        sid = m.group(1)
        episodes.append((int(ep_num), sid))
    return sorted(episodes, key=lambda x: x[0])


def get_zip_path(sub_id: str) -> str:
    dl_html = fetch(f"{BASE}/download-{sub_id}.html")
    m = re.search(
        r"var s1=\s*'([^']*)';\s*.*?var s2=\s*'([^']*)';\s*.*?var s3=\s*'([^']*)';\s*.*?var s4=\s*'([^']*)';",
        dl_html,
        flags=re.DOTALL,
    )
    if not m:
        raise RuntimeError(f"Could not parse download JS for subtitle {sub_id}")
    rel = "".join(m.groups())
    # Encode spaces etc. in filename
    parts = rel.split("/")
    parts[-1] = quote(parts[-1])
    return f"{BASE}/{'/'.join(parts)}"


def srt_to_vtt(srt_text: str) -> str:
    text = srt_text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^\ufeff", "", text)
    blocks = re.split(r"\n\n+", text.strip())
    lines = ["WEBVTT", ""]
    for block in blocks:
        parts = block.strip().split("\n")
        if len(parts) < 2:
            continue
        if parts[0].isdigit():
            parts = parts[1:]
        if not parts:
            continue
        timing = parts[0].replace(",", ".")
        body = "\n".join(parts[1:]).strip()
        if not body:
            continue
        lines.append(timing)
        lines.append(body)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def extract_srt_from_zip(data: bytes) -> str:
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".srt"):
                return zf.read(name).decode("utf-8", errors="replace")
    raise RuntimeError("No .srt in zip")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if TMP_DIR.exists():
        shutil.rmtree(TMP_DIR)
    TMP_DIR.mkdir(parents=True)

    print("Fetching season page...")
    html = fetch(SEASON_URL)
    episodes = parse_episodes(html)
    print(f"Found {len(episodes)} episodes with English subs")

    manifest = {"tmdbId": 2673, "show": "The O.C.", "season": 1, "episodes": {}}

    for ep_num, sub_id in episodes:
        label = f"s01e{ep_num:02d}"
        print(f"  {label} (subtitle id {sub_id})...")
        try:
            zip_url = get_zip_path(sub_id)
            zip_data = fetch_bytes(zip_url)
            srt = extract_srt_from_zip(zip_data)
            vtt = srt_to_vtt(srt)
            out_file = OUT_DIR / f"{label}.vtt"
            out_file.write_text(vtt, encoding="utf-8")
            manifest["episodes"][str(ep_num)] = f"subtitles/the-oc/{label}.vtt"
            time.sleep(0.4)
        except Exception as e:
            print(f"    FAILED: {e}")

    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Done. Wrote {len(manifest['episodes'])} files to {OUT_DIR}")


if __name__ == "__main__":
    main()
