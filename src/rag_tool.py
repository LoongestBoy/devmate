# src/rag_tool.py
import os
from pathlib import Path
from typing import List

from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger
from modelscope import snapshot_download

from config_loader import load_config

# 1. 加载配置
config = load_config()
model_cfg = config.get("model", {})
# 默认回退到 BGE 中文模型 ID
embedding_model_id = model_cfg.get("embedding_model_name", "BAAI/bge-small-zh-v1.5")

# 2. 动态获取根目录并设置本地模型存储路径
ROOT_DIR = Path(__file__).resolve().parent.parent
LOCAL_MODEL_DIR = ROOT_DIR / "embedding_model"

logger.info(f"正在检查本地 Embedding 模型目录: {LOCAL_MODEL_DIR}")

try:
    # 核心逻辑：指定 local_dir 后，如果目录存在且模型完整，将直接返回路径不触发网络请求
    # 如果缺失，则自动从 ModelScope 下载对应文件到该目录
    model_path = snapshot_download(
        model_id=embedding_model_id,
        local_dir=str(LOCAL_MODEL_DIR)
    )
    logger.info(f"模型就绪，加载路径: {model_path}")
except Exception as e:
    logger.error(f"从 ModelScope 获取模型失败，请检查网络: {e}")
    exit(1)

# 使用完全本地的路径初始化 HuggingFaceEmbeddings
embeddings = HuggingFaceEmbeddings(model_name=model_path)

# 3. 动态加载 RAG 相关的路径配置
rag_config = config.get("rag", {})

# 从配置文件读取目录名称，如果未配置则提供默认回退值
docs_dir_name = rag_config.get("docs_dir", "docs")
db_dir_name = rag_config.get("db_dir", ".chroma_db")

DOCS_DIR = ROOT_DIR / docs_dir_name
DB_DIR = ROOT_DIR / db_dir_name

logger.info(f"已加载 RAG 配置 - 文档目录: {DOCS_DIR}, 数据库目录: {DB_DIR}")


def ingest_documents() -> Chroma | None:
    if not DOCS_DIR.exists():
        logger.error(f"路径不存在: {DOCS_DIR}")
        return None

    documents: List[Document] = []
    for filepath in DOCS_DIR.glob("*.md"):
        logger.info(f"正在加载文档: {filepath.name}")
        loader = TextLoader(str(filepath), encoding="utf-8")
        documents.extend(loader.load())

    if not documents:
        logger.warning("没有可用的markdown文件")
        return None

    # 文本切分
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50
    )

    splits = text_splitter.split_documents(documents)
    logger.info(f"文档已切分为 {len(splits)} 个文本块")

    # 存入向量数据库并持久化到本地 .chroma_db 文件夹
    logger.info("正在生成向量 Embeddings 并存入 ChromaDB，请稍候...")
    try:
        vectorstore = Chroma.from_documents(
            documents=splits,
            embedding=embeddings,
            persist_directory=str(DB_DIR)
        )
        logger.info("文档向量化及持久化完成")
        return vectorstore
    except Exception as e:
        logger.error(f"向量数据库初始化失败: {e}")
        return None


def search_knowledge_base(query: str) -> str:
    """
    检索工具：根据用户的查询在本地向量数据库中搜索相关文档。
    """
    logger.info(f"收到本地知识库检索请求，关键词: {query}")
    if not DB_DIR.exists():
        logger.warning("向量数据库未初始化，正在尝试先摄入文档...")
        vectorstore = ingest_documents()
        if not vectorstore:
            return "本地知识库为空或初始化失败。"
    else:
        # 如果已经有数据库了，直接加载
        vectorstore = Chroma(
            persist_directory=str(DB_DIR),
            embedding_function=embeddings
        )

    try:
        # 检索最相关的 2 个片段
        results = vectorstore.similarity_search(query, k=2)
        if not results:
            return "本地知识库中未找到相关内容。"

        formatted_res = "\n\n".join([f"片段:\n{doc.page_content}" for doc in results])
        logger.info("检索成功，已返回相关内容。")
        return formatted_res
    except Exception as e:
        logger.error(f"检索过程发生错误: {e}")
        return f"检索失败: {str(e)}"


if __name__ == "__main__":
    # 测试环境：触发 ingest 并执行检索
    logger.info("开始 RAG 流程测试...")
    q = "project guidelines"
    result = search_knowledge_base(q)

    logger.info("\n>>> 检索结果预览 <<<")
    logger.info(f"\n{result}\n")