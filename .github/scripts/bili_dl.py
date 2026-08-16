#!/usr/bin/env python3
"""Download a bilibili video (anonymous 480p) to {title}.mp4 and write .outname."""
import json
import os
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0"}
REF = {"Referer": "https://www.bilibili.com/"}


def get(url, hdr=None):
    req = urllib.request.Request(url, headers=UA)
    for k, v in (hdr or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    url = os.environ.get("URL", "")
    m = re.search(r"BV[0-9A-Za-z]{10}", url)
    if not m:
        print("no bvid found in URL", file=sys.stderr)
        return 1
    bvid = m.group(0)
    info = get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    if info.get("code") != 0:
        print("view api failed:", info, file=sys.stderr)
        return 1
    cid = info["data"]["cid"]
    title = info["data"]["title"]
    title = re.sub(r'[\\/:*?"<>|]', "_", title).strip() or "bilibili_video"
    pl = get(
        f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&qn=64&fnval=0",
        REF,
    )
    if pl.get("code") != 0 or not (pl.get("data") or {}).get("durl"):
        print("playurl failed:", pl, file=sys.stderr)
        return 1
    stream = pl["data"]["durl"][0]["url"]
    quality = pl["data"].get("quality")
    out = f"{title}.mp4"
    print(f"resolved {title} quality={quality} -> {out}")
    req = urllib.request.Request(stream, headers={**UA, **REF})
    with urllib.request.urlopen(req, timeout=600) as r, open(out, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    with open(".outname", "w", encoding="utf-8") as f:
        f.write(out)
    print("bilibili download done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
