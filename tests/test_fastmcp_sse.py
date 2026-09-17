"""
Tests for dynamic multi-tenant MCP SSE protocol handlers.
"""

import pytest
import mcp.types
from mcp_gateway.core.fastmcp_hub import dynamic_list_tools, dynamic_call_tool


@pytest.mark.asyncio
async def test_dynamic_list_tools_returns_empty_when_no_servers():
    """外部サーバー未登録時は空のツールリストが返却されることを検証。"""
    tools = await dynamic_list_tools()
    assert isinstance(tools, list)
    assert len(tools) == 0


@pytest.mark.asyncio
async def test_dynamic_call_tool_unknown():
    """存在しないツールの呼び出し時にエラーメッセージが返却されることを検証。"""
    contents = await dynamic_call_tool(
        name="completely_unknown_tool",
        arguments={},
    )
    assert isinstance(contents, list)
    assert len(contents) == 1
    assert "Error:" in contents[0].text or "404" in contents[0].text
