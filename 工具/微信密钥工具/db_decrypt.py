#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SQLCipher4 (微信 4.x WCDB) 数据库解密器。

实测本机微信 4.x 使用口令模式：
  - encKey = PBKDF2-HMAC-SHA512(密钥, salt, 256000, 32)
  - macKey = PBKDF2-HMAC-SHA512(encKey, salt^0x3a, 2, 32)
  - 页面 HMAC-SHA512 校验 + AES-256-CBC 分页解密

用法：
  python db_decrypt.py <数据库文件> [输出文件]
  密钥从同目录 db_key.txt 读取，也可用环境变量 DB_KEY 指定。
"""

import hashlib
import hmac as hmac_mod
import os
import struct
import sys

try:
    from Crypto.Cipher import AES
except ImportError:
    print("缺少 pycryptodome")
    sys.exit(1)


PAGE_SIZE = 4096
SALT_SIZE = 16
IV_SIZE = 16
HMAC_SIZE = 64
RESERVE = (IV_SIZE + HMAC_SIZE + 15) // 16 * 16
KEY_SIZE = 32
ITER_COUNT = 256000
SQLITE_HEADER = b"SQLite format 3\x00"


def derive_keys(key, salt):
    enc_key = hashlib.pbkdf2_hmac("sha512", key, salt, ITER_COUNT, KEY_SIZE)
    mac_salt = bytes(b ^ 0x3A for b in salt)
    mac_key = hashlib.pbkdf2_hmac("sha512", enc_key, mac_salt, 2, KEY_SIZE)
    return enc_key, mac_key


def page_hmac(page_buf, mac_key, offset, page_no):
    h = hmac_mod.new(mac_key, digestmod=hashlib.sha512)
    h.update(page_buf[offset : PAGE_SIZE - RESERVE + IV_SIZE])
    h.update(struct.pack("<I", page_no))
    return h.digest()


def decrypt_db(src, key_hex, dst):
    key = bytes.fromhex(key_hex)
    if len(key) != 32:
        raise ValueError("密钥长度错误")

    with open(src, "rb") as f:
        data = f.read()
    if len(data) < PAGE_SIZE:
        raise ValueError(f"文件过小: {src}")
    if data[:16] == SQLITE_HEADER:
        print(f"  跳过（已是明文）: {src}")
        return None

    salt = data[:SALT_SIZE]
    enc_key, mac_key = derive_keys(key, salt)

    total_pages = (len(data) + PAGE_SIZE - 1) // PAGE_SIZE
    with open(dst, "wb") as out:
        out.write(SQLITE_HEADER)
        for page_no in range(total_pages):
            page_buf = data[page_no * PAGE_SIZE : (page_no + 1) * PAGE_SIZE]
            if len(page_buf) < PAGE_SIZE:
                break
            if not any(page_buf):
                out.write(page_buf)
                continue
            offset = SALT_SIZE if page_no == 0 else 0
            expect = page_hmac(page_buf, mac_key, offset, page_no + 1)
            stored = page_buf[PAGE_SIZE - RESERVE + IV_SIZE : PAGE_SIZE - RESERVE + IV_SIZE + HMAC_SIZE]
            if expect != stored:
                raise ValueError(
                    f"第 {page_no + 1} 页 HMAC 校验失败（密钥不正确或文件已损坏）"
                )
            iv = page_buf[PAGE_SIZE - RESERVE : PAGE_SIZE - RESERVE + IV_SIZE]
            ct = page_buf[offset : PAGE_SIZE - RESERVE]
            plain = AES.new(enc_key, AES.MODE_CBC, iv).decrypt(ct)
            out.write(plain)
            out.write(page_buf[PAGE_SIZE - RESERVE :])
    return dst


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    src = sys.argv[1]
    here = os.path.dirname(os.path.abspath(__file__))
    key_hex = os.environ.get("DB_KEY", "")
    if not key_hex:
        with open(os.path.join(here, "db_key.txt"), encoding="utf-8") as f:
            key_hex = f.read().strip()
    dst = sys.argv[2] if len(sys.argv) > 2 else src + ".dec.db"
    result = decrypt_db(src, key_hex, dst)
    if result:
        print(f"OK: {dst} ({os.path.getsize(dst)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
