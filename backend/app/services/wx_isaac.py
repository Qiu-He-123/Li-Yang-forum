"""WxIsaac64 纯 Python 实现（与微信官方 wasm 100% 一致）。

微信朋友圈/视频号的加密图片（响应头 x-enc: 1）使用 WxIsaac64 密钥流 XOR
解密。WeFlow/CipherTalk 等工具都是直接调用微信官方编译的
``wasm_video_decode.wasm``；后端是 Python，为不依赖 node/wasm 运行时，
这里把官方 wasm 中 func735（randinit）和 func734（isaac64 核心）的
指令序列原样嵌入（zlib+base64），用一个小型 WAT 解释器执行。

已用官方 wasm 在 Node 中生成的首轮 randrsl（256 个 64 位值）逐项比对，
256/256 完全一致。

用法::

    from app.services.wx_isaac import wx_isaac_keystream
    ks = wx_isaac_keystream(key, raw_len)   # key: XML 里 media 的 key 属性
    decrypted = bytes(b ^ k for b, k in zip(raw, ks))
"""

from __future__ import annotations

import base64
import json
import os
import struct
import threading
import zlib

M32 = (1 << 32) - 1
M64 = (1 << 64) - 1

# func735 = randinit(flag=1)，func734 = isaac64 核心。
# 指令由 wasm2wat 输出提取（见 _probe_work/gen_wx_isaac_data.py），
# 保留原始顺序与标签语义，压缩后存于同目录 wx_isaac_data.txt。
_DATA_FILE = "wx_isaac_data.txt"


def _load_wat() -> dict[str, list[str]]:
    here = os.path.dirname(os.path.abspath(__file__))
    blob = open(os.path.join(here, _DATA_FILE), "r", encoding="utf-8").read().strip()
    raw = zlib.decompress(base64.b64decode(blob))
    data = json.loads(raw.decode("utf-8"))
    return data


_INSTR = _load_wat()
_INSTR735 = _INSTR["func735.wat"]
_INSTR734 = _INSTR["func734.wat"]


class _WatMachine:
    """Small WAT interpreter for the two embedded functions."""

    __slots__ = ("toks", "locals", "stack", "mem", "pc", "jumps")

    def __init__(self, toks, nlocals):
        self.toks = toks
        self.locals = [0] * nlocals
        self.stack = []
        self.mem = bytearray(8192)
        self.pc = 0
        self.jumps = self._resolve(toks)

    @staticmethod
    def _resolve(toks):
        labels = []
        label_stack = []
        for pc, t in enumerate(toks):
            op = t.split()[0]
            if op in ("loop", "block"):
                lbl = {"kind": op, "start": pc + 1, "end": None}
                labels.append(lbl)
                label_stack.append(lbl)
            elif op == "end":
                label_stack[-1]["end"] = pc + 1
                label_stack.pop()
        jumps = {}
        label_stack = []
        order = 0
        for pc, t in enumerate(toks):
            op = t.split()[0]
            if op in ("loop", "block"):
                label_stack.append(labels[order])
                order += 1
            elif op == "end":
                label_stack.pop()
            elif op in ("br_if", "br"):
                lbl = label_stack[-1 - int(t.split()[1])]
                jumps[(pc, op)] = lbl["start"] if lbl["kind"] == "loop" else lbl["end"]
        return jumps

    def _step(self, cb):
        t = self.toks[self.pc]
        parts = t.split()
        op = parts[0]
        self.pc += 1
        if op == "local.get":
            self.stack.append(self.locals[int(parts[1])])
        elif op == "local.set":
            self.locals[int(parts[1])] = self.stack.pop()
        elif op == "i32.const":
            self.stack.append(int(parts[1]) & M32)
        elif op == "i64.const":
            self.stack.append(int(parts[1]) & M64)
        elif op == "i32.add":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a + b) & M32)
        elif op == "i32.sub":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a - b) & M32)
        elif op == "i32.or":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a | b) & M32)
        elif op == "i32.and":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a & b) & M32)
        elif op == "i32.shl":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a << (b & 31)) & M32)
        elif op == "i32.shr_u":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a >> (b & 31)) & M32)
        elif op == "i32.lt_u":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append(1 if a < b else 0)
        elif op == "i32.eqz":
            self.stack.append(1 if self.stack.pop() == 0 else 0)
        elif op == "i32.wrap_i64":
            self.stack.append(self.stack.pop() & M32)
        elif op == "i64.add":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a + b) & M64)
        elif op == "i64.sub":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a - b) & M64)
        elif op == "i64.xor":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a ^ b) & M64)
        elif op == "i64.shl":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a << (b & 63)) & M64)
        elif op == "i64.shr_u":
            b, a = self.stack.pop(), self.stack.pop()
            self.stack.append((a >> (b & 63)) & M64)
        elif op == "i64.load":
            off = int(parts[1][7:]) if len(parts) > 1 and parts[1].startswith("offset=") else 0
            addr = (self.stack.pop() + off) & M32
            self.stack.append(int.from_bytes(self.mem[addr:addr + 8], "little"))
        elif op == "i64.store":
            off = int(parts[1][7:]) if len(parts) > 1 and parts[1].startswith("offset=") else 0
            val = self.stack.pop()
            addr = (self.stack.pop() + off) & M32
            self.mem[addr:addr + 8] = (val & M64).to_bytes(8, "little")
        elif op == "br_if":
            if self.stack.pop():
                self.pc = self.jumps[(self.pc - 1, "br_if")]
        elif op == "br":
            self.pc = self.jumps[(self.pc - 1, "br")]
        elif op in ("block", "loop", "end"):
            pass
        elif op == "call":
            cb()
        elif op == "unreachable":
            raise RuntimeError("unreachable")
        else:
            raise NotImplementedError(op)

    def run(self, cb, stop_pc=None):
        while self.pc < len(self.toks):
            if stop_pc is not None and self.pc >= stop_pc:
                return
            self._step(cb)


def _nlocals(toks):
    """params + locals: 最大被引用的局部变量下标 + 1。"""
    mx = 0
    for t in toks:
        p = t.split()
        if len(p) > 1 and p[0] in ("local.get", "local.set"):
            mx = max(mx, int(p[1]))
    return mx + 1


_M735 = _WatMachine(_INSTR735, _nlocals(_INSTR735))
_M734 = _WatMachine(_INSTR734, _nlocals(_INSTR734))
_LOCK = threading.Lock()


def _randinit(mem: bytearray) -> None:
    """run func735(flag=1) on the given memory (object base = 0)."""
    _M735.pc = 0
    _M735.stack.clear()
    _M735.locals[:] = [0] * len(_M735.locals)
    _M735.locals[0] = 0  # object base
    _M735.locals[1] = 1  # flag = 1（随机化 randrsl+mm）
    _M735.mem = mem
    _M735.run(_isaac64)


def _isaac64() -> None:
    """run func734 (isaac64 core) on the same memory."""
    _M734.pc = 0
    _M734.stack.clear()
    _M734.locals[:] = [0] * len(_M734.locals)
    _M734.locals[0] = 0
    _M734.mem = _M735.mem
    _M734.run(None)


_CACHE: dict[str, bytearray] = {}
_CACHE_MAX_KEYS = 16
_CACHE_MAX_BYTES = 64 * 1024 * 1024


def wx_isaac_keystream(key: int | str, size: int) -> bytes:
    """生成与微信官方 wasm 一致的 XOR 密钥流（前 size 字节）。

    密钥流只依赖 key，与图片 URL 无关；同一 key 的多次调用会复用已生成的
    流（缓存上限见 _CACHE_MAX_BYTES）。
    """
    with _LOCK:
        key_s = str(key).strip()
        buf = _CACHE.get(key_s)
        if buf is None:
            if len(_CACHE) >= _CACHE_MAX_KEYS:
                _CACHE.clear()
            mem = bytearray(8192)
            seed = int(key_s) & M64
            mem[0:8] = seed.to_bytes(8, "little")
            _randinit(mem)  # 含一次 isaac64，之后 randcnt=256
            buf = bytearray()
            _CACHE[key_s] = buf

        need = size - len(buf)
        if need > 0:
            mem = _M735.mem
            randcnt = int.from_bytes(mem[2048:2056], "little")
            while need > 0:
                if randcnt == 0:
                    _isaac64()
                    randcnt = 256
                randcnt -= 1
                off = randcnt * 8
                v = int.from_bytes(mem[off:off + 8], "little")
                buf += struct.pack(">Q", v)
                need -= 8
                if len(buf) >= _CACHE_MAX_BYTES:
                    break
            mem[2048:2056] = randcnt.to_bytes(8, "little")
        return bytes(buf[:size])
