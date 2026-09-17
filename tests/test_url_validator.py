"""
Unit tests for SSRF URL validation and ServerCreateRequest schema.
"""

from __future__ import annotations

import socket
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from mcp_gateway.schemas.server import ServerCreateRequest
from mcp_gateway.services.url_validator import SSRFValidationError, validate_mcp_url


class TestSSRFValidator:
    """SSRF 防御バリデータの単体テスト。"""

    def test_valid_public_url(self):
        """パブリックな正常 URL は検証を通過する。"""
        # DNS 解決を安全な公開 IP にモック
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
            validate_mcp_url("https://example.com/mcp", allow_local=False)

    def test_invalid_scheme(self):
        """http/https 以外のスキームは拒絶される。"""
        for invalid in ["ftp://example.com/mcp", "file:///etc/passwd", "gopher://evil.com", "ws://example.com"]:
            with pytest.raises(SSRFValidationError, match="Invalid URL scheme"):
                validate_mcp_url(invalid)

    def test_empty_or_invalid_input(self):
        """空文字やホスト名なしは拒絶される。"""
        with pytest.raises(SSRFValidationError, match="URL cannot be empty"):
            validate_mcp_url("")

        with pytest.raises(SSRFValidationError, match="valid hostname"):
            validate_mcp_url("http://")

    def test_blocked_cloud_metadata_ip(self):
        """クラウドメタデータ IP (169.254.169.254, 100.100.100.200) は即時拒絶される。"""
        for meta_ip in ["169.254.169.254", "100.100.100.200"]:
            with patch("socket.getaddrinfo") as mock_dns:
                mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (meta_ip, 80))]
                with pytest.raises(SSRFValidationError, match="cloud metadata IP"):
                    validate_mcp_url(f"http://{meta_ip}/latest/meta-data", allow_local=False)

                # allow_local=True でもメタデータ IP は絶対に許可しない
                with pytest.raises(SSRFValidationError, match="cloud metadata IP"):
                    validate_mcp_url(f"http://{meta_ip}/latest/meta-data", allow_local=True)

    def test_localhost_and_loopback_blocked_by_default(self):
        """allow_local=False の場合、localhost や 127.0.0.1、::1 は拒絶される。"""
        for host in ["localhost", "127.0.0.1", "[::1]", "metadata.google.internal"]:
            with pytest.raises(SSRFValidationError, match="strictly forbidden"):
                validate_mcp_url(f"http://{host}/mcp", allow_local=False)

    def test_private_network_ips_blocked_by_default(self):
        """allow_local=False の場合、プライベート IP (10.x, 192.168.x, 172.16.x) は遮断される。"""
        private_ips = ["10.0.0.1", "192.168.1.50", "172.16.0.10"]
        for ip in private_ips:
            with patch("socket.getaddrinfo") as mock_dns:
                mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 80))]
                with pytest.raises(SSRFValidationError, match="private network IP"):
                    validate_mcp_url("http://internal.service.local/api", allow_local=False)

    def test_allow_local_flag_permits_private_and_loopback(self):
        """allow_local=True の場合、開発用に localhost やプライベート IP への接続が許可される。"""
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 8080))]
            # 例外が発生しないこと
            validate_mcp_url("http://127.0.0.1:8080/mcp", allow_local=True)

        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.1.10", 8080))]
            validate_mcp_url("http://192.168.1.10:8080/mcp", allow_local=True)

    def test_dns_resolution_failure(self):
        """名前解決に失敗したホストは SSRFValidationError となる。"""
        with patch("socket.getaddrinfo", side_effect=socket.gaierror("Name or service not known")):
            with pytest.raises(SSRFValidationError, match="Could not resolve hostname"):
                validate_mcp_url("https://nonexistent-host-xyz123.com/mcp")


class TestServerCreateRequestSchema:
    """Pydantic ServerCreateRequest のバリデーション連携テスト。"""

    def test_valid_request(self):
        """正常な URL であればモデル生成に成功する。"""
        with patch("socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]
            req = ServerCreateRequest(name="Notion MCP", url="https://mcp.notion.example.com")
            assert req.name == "Notion MCP"
            assert req.url == "https://mcp.notion.example.com"

    def test_ssrf_url_raises_validation_error(self):
        """SSRF 検証に失敗する URL を渡すと ValidationError が発生する。"""
        with pytest.raises(ValidationError) as exc_info:
            ServerCreateRequest(name="Malicious MCP", url="http://169.254.169.254/secret")
        assert "SSRF validation failed" in str(exc_info.value)
