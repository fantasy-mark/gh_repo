# -*- coding: utf-8 -*-
"""
gh_api.py - thin GitHub REST API helper used by the DSH "GitHub" tab plugin.
Runs inside the harness sandbox; the plugin Host calls it via shell.run with
PYTHONPATH pointing at .dsh-tools. All network egress goes through python
(urllib), which works under the Windows restricted-token sandbox where curl's
schannel fails.

Usage:
  python gh_api.py <method> <path> [--pat XXX] [--body JSON] [--field k=v ...]
  python gh_api.py upload <repo> <path> <file> [--pat XXX] [--message MSG]
  python gh_api.py download <repo> <path> [--pat XXX] [--out FILE]

REST methods: GET POST PATCH PUT DELETE. `path` is the API path without the
https://api.github.com prefix (may contain :owner/:repo placeholders replaced
by --repo owner/repo). --field k=v appends query params.
"""
import base64
import json
import mimetypes
import os
import sys
import urllib.parse
import urllib.request

API = "https://api.github.com"


def request(method, url, pat=None, body=None, headers=None, timeout=120):
    h = {"User-Agent": "dsh-gh-tab/1.0", "Accept": "application/vnd.github+json"}
    if pat:
        h["Authorization"] = f"Bearer {pat}"
        h["X-GitHub-Api-Version"] = "2022-11-28"
    if headers:
        h.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")
            if "json" in ctype:
                return {"status": r.status, "json": json.loads(raw.decode("utf-8") or "null")}
            return {"status": r.status, "text": raw.decode("utf-8", "replace")}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        try:
            detail = json.loads(detail)
        except Exception:
            pass
        return {"status": e.code, "error": detail, "url": url}
    except Exception as e:
        return {"status": 0, "error": f"{type(e).__name__}: {e}", "url": url}


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        print(json.dumps({"error": "usage: gh_api.py METHOD PATH ..."}))
        return 2
    method = args[0].upper()
    path = args[1]
    pat = None
    body = None
    repo = None
    fields = {}
    out_file = None
    message = None
    body_file = None
    body_b64 = None

    i = 2
    while i < len(args):
        a = args[i]
        if a == "--pat" and i + 1 < len(args):
            pat = args[i + 1]; i += 2
        elif a == "--body" and i + 1 < len(args):
            body = json.loads(args[i + 1]); i += 2
        elif a == "--body-file" and i + 1 < len(args):
            body_file = args[i + 1]; i += 2
        elif a == "--body-b64" and i + 1 < len(args):
            body_b64 = args[i + 1]; i += 2
        elif a == "--repo" and i + 1 < len(args):
            repo = args[i + 1]; i += 2
        elif a == "--field" and i + 2 < len(args):
            k, v = args[i + 1], args[i + 2]
            fields[k] = v; i += 3
        elif a == "--out" and i + 1 < len(args):
            out_file = args[i + 1]; i += 2
        elif a == "--message" and i + 1 < len(args):
            message = args[i + 1]; i += 2
        else:
            i += 1

    if body is None and body_b64:
        import base64 as _b64
        body = json.loads(_b64.b64decode(body_b64).decode("utf-8"))
    elif body is None and body_file:
        with open(body_file, "r", encoding="utf-8-sig") as f:
            body = json.load(f)

    # resolve :owner/:repo placeholders
    if repo and ":owner" in path:
        if "/" not in repo:
            print(json.dumps({"error": f"--repo must be owner/repo, got {repo}"}))
            return 2
        owner, reponame = repo.split("/", 1)
        path = path.replace(":owner", owner).replace(":repo", reponame)

    url = API + path
    if fields:
        url += "?" + urllib.parse.urlencode(fields)

    if method == "UPLOAD" and out_file is None and body is None:
        # upload <repo> <path> <file> --pat --message
        # (method UPLOAD means: PUT file content into a repository file)
        # args: UPLOAD repo path file
        pass

    if method == "DOWNLOAD":
        # download <repo> <path> [--out FILE] --pat
        res = request("GET", url, pat)
        if res.get("status") == 200 and out_file:
            js = res.get("json")
            if isinstance(js, dict) and "content" in js:
                raw = base64.b64decode(js["content"])
            elif isinstance(js, dict) and "download_url" in js and js.get("download_url"):
                dl = request("GET", js["download_url"], pat)
                raw = dl.get("text", "").encode("utf-8") if isinstance(dl.get("text"), str) else dl.get("raw", b"")
                if not isinstance(raw, bytes):
                    raw = str(raw).encode("utf-8")
            else:
                print(json.dumps(res))
                return 0
            with open(out_file, "wb") as f:
                f.write(raw)
            print(json.dumps({"status": 200, "saved": out_file, "bytes": len(raw)}))
            return 0
        print(json.dumps(res))
        return 0

    if method == "PUTFILE":
        # PUTFILE repo path file --pat --message
        if not repo or not out_file:
            print(json.dumps({"error": "PUTFILE needs --repo PATH --out FILE"}))
            return 2
        with open(out_file, "rb") as f:
            content = base64.b64encode(f.read()).decode("ascii")
        payload = {"message": message or "upload via dsh gh tab",
                   "content": content}
        res = request("PUT", url, pat, payload)
        print(json.dumps(res))
        return 0

    if method == "DELFILE":
        # DELFILE repo path --sha XXX --pat --message
        if not repo or not fields.get("sha"):
            print(json.dumps({"error": "DELFILE needs --repo PATH --field sha XXX"}))
            return 2
        payload = {"message": message or "delete via dsh gh tab",
                   "sha": fields["sha"]}
        res = request("DELETE", url, pat, payload)
        print(json.dumps(res))
        return 0

    res = request(method, url, pat, body)
    print(json.dumps(res, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
