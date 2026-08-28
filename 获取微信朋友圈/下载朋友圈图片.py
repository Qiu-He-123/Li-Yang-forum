#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
微信 4.x 朋友圈图片/视频获取（本地缓存解密导出）

配合 获取图片密钥.py 使用：
  1. 先运行 获取图片密钥.py 生成 图片密钥.json
     ※ 前提：必须先在微信朋友圈点开浏览过 2-3 张图片，
       并保持其中一张处于打开状态，才能获取到密钥
  2. 本脚本按密钥里的 wxid 定位对应账号，把 cache/<YYYY-MM>/Sns/ 缓存全部导出：
       - Sns/Img/<hex>/<hash>   V2 加密图片 → 朋友圈图片/<wxid>/<YYYY-MM>/<hash>.<ext>
       - Sns/Video/<hex>/*      明文视频/封面 → 直接复制
  3. 严格校验：区分「头部有效」和「完整图片」（JPEG 以 FF D9 结尾 /
     PNG 以 IEND 结尾），避免 XOR 密钥错误时把花图当成功

用法：
  python 下载朋友圈图片.py
  python 下载朋友圈图片.py --datadir <微信数据目录> --key <密钥json> --out <输出目录>
"""

import argparse
import json
import os
import re
import shutil
import struct
import sys

try:
    from Crypto.Cipher import AES
    from Crypto.Util import Padding
except ImportError:
    print("缺少 pycryptodome，请先: pip install pycryptodome")
    sys.exit(1)


V2_MAGIC = b"\x07\x08V2\x08\x07"
V1_MAGIC = b"\x07\x08V1\x08\x07"
V1_AES_KEY = b"cfcd208495d565ef"  # 社区公开的 V1 过渡期固定密钥


def normalize_wxid(account_id):
    """wxid_xxx_abcd -> wxid_xxx（去掉 4 位随机后缀）。"""
    aid = (account_id or "").strip()
    if aid.lower().startswith("wxid_"):
        m = re.match(r"^(wxid_[^_]+)", aid, re.IGNORECASE)
        return m.group(1) if m else aid
    return aid


def aligned_aes_size(aes_size):
    rem = (aes_size % 16 + 16) % 16
    return aes_size + (16 - rem)


def detect_format(header):
    if header[:3] == b"\xFF\xD8\xFF":
        return "jpg"
    if header[:4] == b"\x89PNG":
        return "png"
    if header[:3] == b"GIF":
        return "gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "webp"
    if header[:2] == b"BM":
        return "bmp"
    if header[:4] == b"wxgf":
        return "hevc"
    return None


def is_complete_image(data, fmt):
    if not data:
        return False
    if fmt == "jpg":
        return data[-2:] == b"\xFF\xD9"
    if fmt == "png":
        return data[-8:] == b"\x49\x45\x4E\x44\xAE\x42\x60\x82"
    if fmt == "gif":
        return data[-1:] == b"\x3B"
    return False


def decrypt_dat_file(path, aes_key, xor_key):
    """解密单个缓存文件，返回 (bytes, 格式) 或 (None, None)。"""
    with open(path, "rb") as f:
        data = f.read()
    if len(data) < 6:
        return None, None

    head = data[:6]
    if head in (V2_MAGIC, V1_MAGIC):
        key = V1_AES_KEY if head == V1_MAGIC else aes_key
        if not key or len(key) < 16:
            return None, None
        if len(data) < 15:
            return None, None
        aes_size, xor_size = struct.unpack_from("<LL", data, 6)
        aligned = aligned_aes_size(aes_size)
        off = 15
        if off + aligned > len(data):
            return None, None
        try:
            dec_aes = Padding.unpad(
                AES.new(key[:16], AES.MODE_ECB).decrypt(data[off:off + aligned]),
                AES.block_size)
        except ValueError:
            return None, None
        off += aligned
        raw_end = len(data) - xor_size
        raw = data[off:raw_end] if off < raw_end else b""
        xored = data[raw_end:]
        if xor_key is not None:
            xored = bytes(b ^ xor_key for b in xored)
        result = dec_aes + raw + xored
        return result, detect_format(result[:16])

    # 旧 XOR 格式：试常用图片魔数反推单字节密钥
    magics = [(b"\xFF\xD8\xFF", "jpg"), (b"\x89PNG", "png"),
              (b"GIF", "gif"), (b"RIFF", "webp"), (b"BM", "bmp")]
    for magic, fmt in magics:
        if len(data) < len(magic):
            continue
        k = data[0] ^ magic[0]
        if all(i < len(data) and (data[i] ^ k) == magic[i]
               for i in range(len(magic))):
            result = bytes(b ^ k for b in data)
            return result, fmt
    return None, None


def main():
    ap = argparse.ArgumentParser(description="微信4.x 朋友圈图片获取")
    ap.add_argument("--datadir", help="微信数据目录，默认自动检测")
    ap.add_argument("--key", help="图片密钥 json（默认 图片密钥.json）")
    ap.add_argument("--account-dir", help="指定账号目录名（默认按密钥 json 的 wxid 自动定位）")
    ap.add_argument("--out", help="输出目录（默认 朋友圈图片）")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    data_root = args.datadir
    if not data_root:
        for r in (r"D:\Users\Documents\xwechat_files",
                  os.path.expandvars(r"%USERPROFILE%\Documents\xwechat_files")):
            if os.path.isdir(r):
                data_root = r
                break
    if not data_root or not os.path.isdir(data_root):
        print("找不到微信数据目录")
        return 1

    key_path = os.path.abspath(args.key or os.path.join(here, "图片密钥.json"))
    if not os.path.isfile(key_path):
        print("缺少 %s，请先运行 获取图片密钥.py" % key_path)
        return 1
    with open(key_path, encoding="utf-8") as f:
        cfg = json.load(f)
    aes_raw = cfg.get("aes_key", "")
    aes_key = bytes.fromhex(aes_raw) if len(aes_raw) == 32 else \
        aes_raw.encode("ascii")[:16]
    xor_key = cfg.get("xor_key")
    print("AES 密钥: %s" % (aes_raw or aes_key.hex()))
    print("XOR 密钥: %s" % ("0x%02x" % xor_key if xor_key is not None else "无"))

    # 按密钥所属 wxid 定位账号目录（图片密钥是每个账号独立的）
    acc_dir = args.account_dir
    if not acc_dir:
        target_wxid = (cfg.get("wxid") or "").strip()
        if target_wxid:
            try:
                for entry in sorted(os.listdir(data_root)):
                    p = os.path.join(data_root, entry)
                    if not os.path.isdir(p):
                        continue
                    norm = entry
                    if norm.lower().startswith("wxid_"):
                        norm = norm.rsplit("_", 1)[0]
                    if norm == target_wxid:
                        acc_dir = entry
                        break
            except OSError:
                pass
        if not acc_dir:
            print("无法根据密钥 json 定位账号目录（wxid=%s），"
                  "请用 --account-dir 指定" % target_wxid)
            return 1
    data_root = os.path.join(data_root, acc_dir)
    print("账号目录: %s" % data_root)

    out_root = os.path.abspath(args.out or os.path.join(here, "朋友圈图片"))
    out_root = os.path.join(out_root, normalize_wxid(acc_dir))
    os.makedirs(out_root, exist_ok=True)

    total = success = complete = fail = copied = 0
    for dp, _dn, fns in os.walk(data_root):
        parts = dp.split(os.sep)
        if "Sns" not in parts:
            continue
        month = next((x for x in reversed(parts) if len(x) == 7 and x[4] == "-"),
                     "")
        kind = "Video" if "Video" in parts else "Img" if "Img" in parts else None
        if kind is None:
            continue
        month_out = os.path.join(out_root, month) if month else out_root
        os.makedirs(month_out, exist_ok=True)
        for fn in fns:
            src = os.path.join(dp, fn)
            base = fn
            if base.endswith("_t"):
                continue  # 跳过缩略图
            if base.endswith("_d"):
                base = base[:-2]
            total += 1
            if kind == "Video":
                dst = os.path.join(month_out, base)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                copied += 1
                continue
            img, fmt = decrypt_dat_file(src, aes_key, xor_key)
            if not img or not fmt:
                fail += 1
                continue
            if is_complete_image(img, fmt):
                complete += 1
            dst = os.path.join(month_out, base + "." + fmt)
            with open(dst, "wb") as f:
                f.write(img)
            # 保留原缓存文件的修改时间，供导出器按时间窗口匹配动态
            os.utime(dst, (os.path.getatime(src), os.path.getmtime(src)))
            success += 1

    print("完成: 共 %d 个文件" % total)
    print("  图片解密成功: %d（其中完整图片 %d 张）" % (success, complete))
    print("  视频/封面复制: %d" % copied)
    print("  失败: %d" % fail)
    if success and complete < success:
        print("  注: 部分图片头部有效但结尾不完整（缩略图/未下载完整），"
              "这是微信缓存本身的特性")
    print("输出: %s" % out_root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
