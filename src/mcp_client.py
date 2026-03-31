# src/mcp_client.py
import asyncio
import os
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from loguru import logger
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

async def run_client_test() -> None:
    """运行 MCP 客户端测试，尝试调用 Server 端的搜索工具。"""
    logger.info("正在初始化 MCP 客户端...")

    client_config = {
        "search_server": {
            "transport": "streamable-http",
            "url": "http://127.0.0.1:8000/mcp"
        }
    }

    try:
        client = MultiServerMCPClient(client_config)
        logger.info("准备连接到 Server...")

        # 核心改动：使用官方推荐的 session 上下文管理器，确保连接稳定不断开
        async with client.session("search_server") as session:
            logger.info("成功建立稳定会话，正在获取工具列表...")
            # 使用 load_mcp_tools 替代原来的 client.get_tools()
            tools = await load_mcp_tools(session)

            target_tool = None
            for tool in tools:
                if tool.name == "search_web":
                    target_tool = tool
                    break

            if not target_tool:
                logger.error("在 Server 端未找到 search_web 工具！")
                return

            logger.info(">>> 开始测试 search_web 工具 <<<")
            test_query = "LangChain 2026 最新特性"

            # 异步调用工具
            result = await target_tool.ainvoke({"query": test_query})

            logger.info(">>> 测试成功！搜索结果预览 <<<")
            logger.info(f"\n{str(result)[:300]}...\n")

    except Exception as e:
        logger.error(f"MCP 客户端测试失败，请检查 Server 是否正在运行。详细错误: {e}")


if __name__ == "__main__":
    asyncio.run(run_client_test())