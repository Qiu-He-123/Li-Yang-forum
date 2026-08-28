# -*- coding: utf-8 -*-
"""向微信“朋友圈”窗口模拟点击，不移动真实鼠标。

原理：直接用 PostMessage 给窗口发 WM_LBUTTONDOWN / WM_LBUTTONUP，
消息里的坐标由 lParam 携带，Windows 不会把物理光标移过去。
注意：微信对投递的点击有输入来源校验，窗口不在前台时经常忽略——
所以点击前会先把“朋友圈”窗口带到前台获取焦点（最小化则还原），
点完再把焦点还给用户原来的窗口（可关闭）。

除命令行手动触发外，还提供可复用的刷新算法：
    refresh_moments_cache(click_pos=(96, 19), settle_seconds=4, max_wait=15)
流程：定位朋友圈窗口 -> 获取焦点 -> 模拟点击刷新入口 -> 等 sns.db 写入
稳定 -> 返回是否已刷新。同步客户端在读取朋友圈数据库前调用它。
"""

import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
MK_LBUTTON = 0x0001
WM_VSCROLL = 0x0115
SB_TOP = 6

SW_SHOW = 5
SW_RESTORE = 9
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002

# 给用到的函数显式声明参数/返回类型（HWND 在 64 位下是 64 位值，
# 不声明会被 ctypes 按 32 位 int 截断，导致句柄失效）
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetForegroundWindow.restype = wt.BOOL
user32.BringWindowToTop.argtypes = [wt.HWND]
user32.BringWindowToTop.restype = wt.BOOL
user32.IsIconic.argtypes = [wt.HWND]
user32.IsIconic.restype = wt.BOOL
user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.ShowWindow.restype = wt.BOOL
user32.GetForegroundWindow.restype = wt.HWND
user32.SetActiveWindow.argtypes = [wt.HWND]
user32.SetActiveWindow.restype = wt.HWND
user32.SetFocus.argtypes = [wt.HWND]
user32.SetFocus.restype = wt.HWND
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.AttachThreadInput.restype = wt.BOOL
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wt.DWORD, ctypes.c_ulong]

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def _set_foreground(hwnd):
    """把窗口设为前台。先按一下 Alt 绕过系统前台锁定（经典技巧）。"""
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    return user32.SetForegroundWindow(hwnd)


def focus_window(hwnd):
    """把“朋友圈”窗口带到前台并获取焦点（最小化则还原）。

    返回 True=已成为前台窗口，False=没能抢到前台（仍继续投递，尽力而为）。
    """
    if not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
        time.sleep(0.15)
    user32.ShowWindow(hwnd, SW_SHOW)
    user32.BringWindowToTop(hwnd)
    ok = _set_foreground(hwnd)
    if not ok:
        # 兜底：把输入线程绑到目标窗口线程再激活，绕过前台限制
        try:
            fg = user32.GetForegroundWindow()
            ftid = user32.GetWindowThreadProcessId(fg, None)
            tid = user32.GetWindowThreadProcessId(hwnd, None)
            if tid != ftid:
                user32.AttachThreadInput(ftid, tid, True)
                user32.SetActiveWindow(hwnd)
                user32.SetFocus(hwnd)
                user32.BringWindowToTop(hwnd)
                user32.AttachThreadInput(ftid, tid, False)
            else:
                user32.SetActiveWindow(hwnd)
                user32.SetFocus(hwnd)
        except Exception:
            pass
    time.sleep(0.2)  # 等窗口完成激活
    return user32.GetForegroundWindow() == hwnd


def restore_focus(hwnd):
    """把焦点还给之前的前台窗口（点完调用，避免一直占用用户屏幕）。"""
    if hwnd and user32.IsWindow(hwnd) and hwnd != user32.GetForegroundWindow():
        _set_foreground(hwnd)


def process_name(pid):
    """通过 PID 拿进程名（比如 WeChat.exe）。"""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return "?"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wt.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return buf.value.rsplit("\\", 1)[-1]
        return "?"
    finally:
        kernel32.CloseHandle(h)


def list_windows():
    """枚举所有可见顶层窗口，返回标题相关的信息。"""
    result = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    @WNDENUMPROC
    def callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        result.append((hwnd, buf.value, pid.value, rect))
        return True

    user32.EnumWindows(callback, 0)
    return result


def find_moments_window():
    """找一个标题包含“朋友圈”的可见窗口。"""
    candidates = []
    for hwnd, title, pid, rect in list_windows():
        if "朋友圈" in title:
            candidates.append((hwnd, title, pid, rect))
    return candidates


def click_client(hwnd, x, y):
    """在窗口客户区坐标 (x, y) 处模拟一次左键点击。"""
    # 先把客户区原点换算成屏幕坐标，方便核对点落在哪
    pt = wt.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))

    # lParam 低 16 位是 x，高 16 位是 y
    lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)

    r1 = user32.PostMessageW(hwnd, WM_MOUSEMOVE, 0, lparam)
    time.sleep(0.05)
    r2 = user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
    time.sleep(0.08)
    r3 = user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)

    print(f"  鼠标消息已投递: move={bool(r1)} down={bool(r2)} up={bool(r3)}")
    return r1 and r2 and r3


def scroll_moments_top(hwnd):
    """先把朋友圈列表滚回顶部，让刷新入口可见（部分版本顶部即刷新区）。"""
    user32.PostMessageW(hwnd, WM_VSCROLL, SB_TOP, 0)
    time.sleep(0.3)


def _sns_db_mtime(sns_src):
    try:
        return os.path.getmtime(sns_src) if sns_src and os.path.isfile(sns_src) else None
    except OSError:
        return None


def refresh_moments_cache(
    sns_src=None,
    click_pos=(96, 19),
    wait_seconds=0.8,
    quiet=False,
    restore_after=True,
):
    """刷新朋友圈并等数据库写入稳定。

    算法：
      1. 找到标题含“朋友圈”的微信窗口（没打开朋友圈页面则返回 False 并提示）
      2. 先获取窗口焦点（最小化则还原；微信对无焦点窗口的投递点击经常忽略），
         再滚到列表顶部 + 模拟点击刷新入口（微信收到点击后向服务器拉取最新动态，
         写入本机 sns.db 缓存）
      3. 点完把焦点还给用户原来的窗口（restore_after=False 可关闭）
      4. 等待 wait_seconds 秒给微信拉取/写入时间，然后返回（读取方立即读库）

    返回 True=已执行刷新，False=没找到窗口/点击失败。
    """
    candidates = find_moments_window()
    if not candidates:
        # 静默模式下不打印（调用方会自行节流提示），避免每 3 秒刷屏
        return False

    hwnd, title, pid, rect = candidates[0]
    if not quiet:
        print(f"  刷新朋友圈：HWND=0x{hwnd & 0xFFFFFFFF:08X} | {process_name(pid)} | {title}")

    # 点击前获取焦点（微信对投递的点击有前台校验，无焦点经常不响应）
    prev_fg = user32.GetForegroundWindow()
    if not quiet:
        got = focus_window(hwnd)
        print(f"  朋友圈窗口焦点：{'已获取' if got else '未能获取（继续尝试投递）'}")
    else:
        focus_window(hwnd)

    before = _sns_db_mtime(sns_src)
    scroll_moments_top(hwnd)
    if not click_client(hwnd, click_pos[0], click_pos[1]):
        if not quiet:
            print("  刷新朋友圈：点击消息投递失败，窗口句柄可能已失效")
        if restore_after and prev_fg and prev_fg != hwnd:
            restore_focus(prev_fg)
        return False

    # 点完把焦点还给用户原来的窗口，不一直占用屏幕
    if restore_after and prev_fg and prev_fg != hwnd:
        restore_focus(prev_fg)

    # 给微信服务器拉取 + 写库的时间（实测 3-6 秒），然后由调用方读取
    if not quiet:
        print(f"  刷新朋友圈：等待 {wait_seconds}s 供微信更新本地缓存…")
    time.sleep(wait_seconds)
    after = _sns_db_mtime(sns_src)
    if not quiet:
        if after is not None and before is not None and after != before:
            print("  刷新朋友圈：sns.db 已更新")
        else:
            print("  刷新朋友圈：等待完成（无新动态时数据库可能不变）")
    return True


def main():
    x, y = 96, 19
    print("当前可见窗口列表（找“朋友圈”）：")
    for hwnd, title, pid, rect in list_windows():
        if any(k in title for k in ("微信", "朋友圈", "WeChat", "Weixin", "Moments")):
            print(f"  HWND=0x{hwnd & 0xFFFFFFFF:08X} | {process_name(pid):<14} | "
                  f"{title} | 窗口({rect.left},{rect.top})-({rect.right},{rect.bottom})")

    refresh_moments_cache(click_pos=(x, y))


if __name__ == "__main__":
    main()
