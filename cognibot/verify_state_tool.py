import asyncio
import json
import os
from cognibot.config import load_config
from cognibot.mcp_client import MCPBridge

async def main():
    config = load_config()
    bridge = MCPBridge(config)
    try:
        print("Connecting to MCP bridge...")
        await bridge.connect()
        print("Calling ros2_query_state...")
        result = await bridge.call_tool("ros2_query_state", {})
        print("\n--- Result ---")
        for block in result.get("content", []):
            if block["type"] == "text":
                try:
                    # Try to pretty print if it's JSON
                    data = json.loads(block["text"])
                    print(json.dumps(data, indent=2))
                except Exception:
                    print(block["text"])
        print("--------------\n")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await bridge.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
