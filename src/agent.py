# src/agent.py
import asyncio
import os
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from loguru import logger

from config_loader import load_config
from rag_tool import search_knowledge_base

# 禁用本地代理，防止 MCP 的本地 Streamable HTTP 通信被拦截
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

# 1. 加载配置并注入环境变量 (激活 LangSmith 链路追踪)
config = load_config()
model_cfg = config.get("model", {})
langsmith_cfg = config.get("langsmith", {})
skills_cfg = config.get("skills", {})

if langsmith_cfg.get("langchain_tracing_v2"):
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = langsmith_cfg.get("langchain_api_key", "")
    os.environ["LANGCHAIN_PROJECT"] = langsmith_cfg.get("langchain_project", "devmate")

# 2. 初始化目录
ROOT_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT_DIR / skills_cfg.get("skills_dir", ".skills")
SKILLS_DIR.mkdir(parents=True, exist_ok=True)

# 3. 初始化 LLM (遵循红线要求：必须使用 ChatOpenAI 类调用)
llm = ChatOpenAI(
    model=model_cfg.get("model_name", "gpt-4o-mini"),
    api_key=model_cfg.get("api_key", ""),
    base_url=model_cfg.get("ai_base_url", ""),
    streaming=True,
)


# ==========================================
# 4. 定义 Agent 工具 (Tools)
# ==========================================

@tool
def search_local_docs(query: str) -> str:
    """搜索本地知识库文档，获取内部项目规范、最佳实践或模板要求。"""
    logger.info(f"[Agent 调用工具] 搜索本地文档: '{query}'")
    # 【终极修复】：挂着 async 的羊头，卖着同步的狗肉！
    # 骗过 LangGraph 不派生后台线程，直接在主事件循环中同步执行，彻底封杀 Chroma 的 Rust 线程 Bug
    return search_knowledge_base(query)


@tool
def write_to_file(file_path: str, content: str) -> str:
    """在项目目录中创建或覆盖写入文件。用于生成代码文件或配置文件。"""
    try:
        target_path = ROOT_DIR / file_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[Agent 调用工具] 成功生成文件: {file_path}")
        return f"已成功将代码写入 {file_path}"
    except Exception as e:
        logger.error(f"写入文件 {file_path} 失败: {e}")
        return f"写入文件时发生错误: {e}"


@tool
def save_skill(skill_name: str, task_pattern: str, solution: str) -> str:
    """将成功解决问题的模式保存为可复用的技能 (Skill)，以便未来直接调用。"""
    try:
        skill_path = SKILLS_DIR / f"{skill_name}.txt"
        content = f"【任务模式】\n{task_pattern}\n\n【解决方案与代码结构】\n{solution}"
        with open(skill_path, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info(f"[Agent 调用工具] 习得并保存新技能: {skill_name}")
        return f"成功保存技能: {skill_name}"
    except Exception as e:
        logger.error(f"保存技能失败: {e}")
        return f"保存技能时发生错误: {e}"


def load_existing_skills() -> str:
    """加载之前习得的所有技能，注入到 Agent 的系统提示词中。"""
    skills_text = ""
    for skill_file in SKILLS_DIR.glob("*.txt"):
        with open(skill_file, "r", encoding="utf-8") as f:
            skills_text += f"\n--- 技能: {skill_file.stem} ---\n{f.read()}\n"
    return skills_text


# ==========================================
# 5. 构建与运行 Agent
# ==========================================

async def run_agent(user_prompt: str) -> None:
    logger.info("正在唤醒 DevMate 智能体...")

    # 配置 MCP 客户端，连接到我们之前写好的 Server
    mcp_config = {
        "search_server": {
            "transport": "streamable-http",
            "url": "http://127.0.0.1:8000/mcp"
        }
    }

    try:
        mcp_client = MultiServerMCPClient(mcp_config)
        async with mcp_client.session("search_server") as session:
            logger.info("已成功连接到 MCP 网络搜索节点。")

            # 动态加载 MCP 工具 (Tavily 搜索)
            mcp_tools = await load_mcp_tools(session)

            # 组合所有能力
            tools = mcp_tools + [search_local_docs, write_to_file, save_skill]

            # 构建强大的 System Prompt (赋予系统目标和行为准则)
            existing_skills = load_existing_skills()
            sys_msg = (
                "你是 DevMate，一个强大的 AI 编程助手。\n"
                "【你的工作流准则】：\n"
                "1. 行动前，优先使用 search_local_docs 检索内部开发规范和模板。\n"
                "2. 如果遇到不熟悉的最新技术或错误，使用 search_web (MCP) 进行全网搜索。\n"
                "3. 规划完成后，直接使用 write_to_file 工具为您生成具体的代码和配置文件。\n"
                "4. 如果你发现当前任务非常有通用性，使用 save_skill 工具将解决方案保存下来。"
            )

            if existing_skills:
                sys_msg += f"\n\n【你已掌握的扩展技能】：\n{existing_skills}"

            # 使用 LangGraph 构建现代化的 ReAct 工作流
            agent = create_react_agent(llm, tools)

            logger.info(f"========== 收到任务 ==========\n{user_prompt}\n==============================")

            initial_messages = [
                SystemMessage(content=sys_msg),
                HumanMessage(content=user_prompt)
            ]
            # 开始流式执行 Agent
            async for chunk in agent.astream({"messages": initial_messages}):
                if "agent" in chunk:
                    msg = chunk["agent"]["messages"][0]
                    if msg.content:
                        logger.info(f"DevMate 思考中: {msg.content}")
                elif "tools" in chunk:
                    logger.info("DevMate 正在执行工具链操作...")

            logger.info("✅ 任务执行完毕！请检查根目录是否生成了相关文件。")


    except ExceptionGroup as eg:

        for i, sub_e in enumerate(eg.exceptions):
            logger.error(f"底层的真正报错 [{i}]: {repr(sub_e)}")

    except Exception as e:

        logger.error(f"DevMate 运行崩溃: {e}")

if __name__ == "__main__":
    # 考核清单终极验证：拉取真实 anthropics/skills 仓库规范并重构项目
    test_task = (
        "【真实 Anthropic Skill 汲取与应用】\n"
        "1. 请立刻调用网络搜索工具 (search_web/MCP)，去搜索 GitHub 上 `anthropics/skills` 仓库中名为 `web-artifacts-builder` 的核心前端技术栈要求。\n"
        "2. 根据搜索结果，调用 `save_skill` 工具，将其保存为 `real_web_artifacts_builder`。Task pattern 写：构建现代化复杂前端页面时。Solution 必须包含它要求的核心技术栈（React, Tailwind CSS, shadcn/ui 等）。\n"
        "3. 接下来，应用这个刚学到的技能！请用 `write_to_file` 工具，将我们项目里 `web/index.html` 的前端代码彻底重构。\n"
        "4. 【重构约束】：由于我们当前没有配置 Vite 打包环境，请你通过引入 React 和 Tailwind CSS 的 CDN 链接，在 `web/index.html` 单文件中用 React 组件的方式重写那个'徒步路线页面'。让它看起来具有现代化、极简的 shadcn/ui 风格！"
    )
    asyncio.run(run_agent(test_task))