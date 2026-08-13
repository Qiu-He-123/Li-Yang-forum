"""从官方 wasm 的 WAT 提取 func735/func734 指令并生成数据文件。"""

import base64
import json
import os
import re
import zlib


HERE = os.path.dirname(os.path.abspath(__file__))
WAT = os.path.join(HERE, "wasm_video_decode.wat")
OUT = os.path.join(os.path.dirname(HERE), "backend", "app", "services", "wx_isaac_data.txt")


def extract(fid):
    data = open(WAT, "r", encoding="utf-8", errors="replace").read()
    start = data.find(f"(func (;{fid};)")
    nxt = data.find("(func", start + 10)
    end = nxt if nxt > 0 else data.find("\n)", start)
    body = data[start:end]
    body = body[body.find("local.get"):]
    lines = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(";;"):
            continue
        line = re.sub(r"\(;[^)]*;\)", "", line).strip()
        if line.endswith(")"):
            line = line[:-1].strip()
        if line:
            lines.append(line)
    return lines


def main():
    out = {"func735.wat": extract(735), "func734.wat": extract(734)}
    blob = base64.b64encode(
        zlib.compress(json.dumps(out, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 9)
    ).decode()
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(blob)
    print("wrote", OUT, "blob len", len(blob))
    for k, v in out.items():
        print(k, len(v))


if __name__ == "__main__":
    main()
