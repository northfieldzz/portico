"""
IT Context Platform — SSRF (Server-Side Request Forgery) Prevention Validator
外部 MCP サーバー等の登録・接続先 URL を検査し、プライベート/メタデータ IP への通信を阻止する。
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# 明示的にブロックする危険なメタデータ IP
BLOCKED_EXACT_IPS = {
    "169.254.169.254",  # AWS/GCP/Azure Instance Metadata
    "100.100.100.200",  # Alibaba Cloud Metadata
}


class SSRFValidationError(ValueError):
    """SSRF 脆弱性リスクを含む不正な URL が指定された場合の例外。"""

    pass


def validate_mcp_url(url: str, allow_local: bool = False) -> None:
    """
    指定された URL のホスト名および解決先 IP アドレスを検査する。

    :param url: 検証対象の URL (e.g. "https://mcp.external.example.com/sse")
    :param allow_local: ローカル開発環境シミュレータでのプライベート IP 許可フラグ
    :raises SSRFValidationError: 禁止された IP 帯またはスキーマの場合
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError("URL cannot be empty")

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SSRFValidationError(f"Invalid URL scheme '{parsed.scheme}'. Only http/https are allowed.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError("URL must include a valid hostname")

    # ホスト名文字列での簡易チェック
    lower_host = hostname.lower()
    if not allow_local and lower_host in ("localhost", "127.0.0.1", "::1", "metadata.google.internal"):
        raise SSRFValidationError(f"Access to localhost/internal host '{hostname}' is strictly forbidden (SSRF)")

    # DNS 解決と IP アドレスのレンジ検査
    try:
        addr_info = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SSRFValidationError(f"Could not resolve hostname '{hostname}': {exc}") from exc

    for item in addr_info:
        ip_str = item[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if getattr(ip, "ipv4_mapped", None):
            ip = ip.ipv4_mapped
            ip_str = str(ip)

        if ip_str in BLOCKED_EXACT_IPS:
            raise SSRFValidationError(f"Access to cloud metadata IP '{ip_str}' is strictly forbidden (SSRF)")

        if not allow_local:
            # SECURITY: Unspecified IPs (0.0.0.0, ::) evaluate to False for is_private in some cases
            # and must be explicitly blocked to prevent SSRF bypass.
            if getattr(ip, "is_unspecified", False) and ip.is_unspecified:
                raise SSRFValidationError(f"Access to unspecified IP '{ip_str}' is forbidden (SSRF)")
            if ip.is_loopback:
                raise SSRFValidationError(f"Access to loopback IP '{ip_str}' is forbidden (SSRF)")
            if ip.is_private:
                raise SSRFValidationError(f"Access to private network IP '{ip_str}' is forbidden (SSRF)")
            if ip.is_link_local:
                raise SSRFValidationError(f"Access to link-local IP '{ip_str}' is forbidden (SSRF)")
            if ip.is_multicast or ip.is_reserved:
                raise SSRFValidationError(f"Access to reserved/multicast IP '{ip_str}' is forbidden (SSRF)")
            if not getattr(ip, "is_global", False):
                raise SSRFValidationError(f"Access to non-global IP '{ip_str}' is forbidden (SSRF)")

    logger.debug("✅ MCP URL '%s' passed SSRF validation", url)
