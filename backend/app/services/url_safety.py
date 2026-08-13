"""SSRF 防护：禁止 AI/DeepSeek 等可配置 base_url 指向内网/保留地址。

背景：管理员可在后台配置 AI base_url，若被诱导指向内网（如云元数据
169.254.169.254、内网管理端口），后端会把带 API Key 的请求打到内网。

策略：
- 解析 host 的所有 A/AAAA 记录，命中内网/回环/链路本地/保留/组播地址一律拒绝
- 域名解析失败一律拒绝（防 DNS rebinding 先解析后连接）
- 只允许公网目标
"""
import ipaddress
import socket
from urllib.parse import urlparse

from loguru import logger

# 显式补充 ipaddress 的 is_private 等未覆盖的保留段
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),   # CGNAT
    ipaddress.ip_network("192.0.0.0/24"),    # IETF 协议分配
    ipaddress.ip_network("198.18.0.0/15"),   # 基准测试
    ipaddress.ip_network("::ffff:0:0/96"),   # IPv4-mapped
]


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """单个 IP 是否属于内网/保留/回环/链路本地地址。"""
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    for net in _BLOCKED_NETWORKS:
        if ip in net:
            return True
    return False


def is_private_host(host: str) -> bool:
    """解析 host 的所有地址，任一命中内网即视为不安全（保守策略）。"""
    if not host:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        # 解析失败一律拒绝，避免 DNS rebinding / 通配域名绕过
        logger.warning("[SSRF] 域名解析失败，拒绝连接: {}", host)
        return True
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if is_blocked_ip(ip):
            return True
    return False


def validate_public_url(url: str) -> bool:
    """校验 URL 可安全外呼：仅允许 https 且 host 解析到公网地址。"""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return False
    host = parsed.hostname
    if not host:
        return False
    return not is_private_host(host)
