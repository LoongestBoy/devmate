from loguru import logger
from mcp.server.fastmcp import FastMCP
from  tavily import TavilyClient

from config_loader import load_config

# 加载配置
config = load_config()
tavily_api_key= config.get("search",{}).get("tavily_api_key","")

if not tavily_api_key:
    logger.error("未在config.toml中找到tavily_api_key")
    exit(1)


# 初始化tavily客户端
tavily_client = TavilyClient(api_key=tavily_api_key)

# 初始化FastMCP客户端

mcp = FastMCP("DevMateSearch", host = "127.0.0.1", port = 8000)


@mcp.tool()
def search_web(query:str)->str:
    logger.info(f"查询关键词:{query}")
    try:
        response = tavily_client.search(query = query)
        results = response.get("results",[])

        if not results:
            logger.warning(f"未找到{query}有关信息")
            return "没有找到相关的网络搜索结果"

        #格式化结果为纯文本
        formatted_list = []
        for res in results:
            title = res.get("title","无标题")
            url = res.get("url", "无链接")
            content = res.get("content", "无内容")
            formatted_list.append(f"标题: {title}\n链接: {url}\n内容: {content}")

        logger.info("搜索成功，返回格式化结果")
        return "\n\n".join(formatted_list)
    except Exception as e:
        logger.error(f"搜索过程错误：{e}")
        return f"搜索失败：{str(e)}"


if __name__ == "__main__":
    logger.info("MCP搜索启动中")
    mcp.run(transport="streamable-http")
