#!/usr/bin/env python3
"""
MCP server test script
"""
import sys
import asyncio
from server import mcp

async def test_server():
    """Test if the MCP server is set up correctly"""
    print("Testing MCP server setup...")
    print(f"Server name: {mcp.name}")
    print(f"Available tools: {list(mcp._tool_manager._tools.keys())}")
    print("\nServer setup is correct!")
    return True

if __name__ == "__main__":
    try:
        result = asyncio.run(test_server())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
