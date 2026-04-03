# src/chat_server.py
import os
import sqlite3
import json
import traceback
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage, AIMessage

from agent import (
    llm,
    load_existing_skills,
    search_local_docs,
    write_to_file,
    save_skill
)

tools = [search_local_docs, write_to_file, save_skill]

app = FastAPI(title="DevMate Pro API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确保数据库文件夹存在
db_folder = "chat_history"
db_path = os.path.join(db_folder, "chat_history.db")
os.makedirs(db_folder, exist_ok=True)

conn = sqlite3.connect(db_path, check_same_thread=False)
memory = SqliteSaver(conn)
memory.setup()

system_prompt = "你是一个强大的全栈 AI 编程助手。请直接、清晰地回答问题。\n" + load_existing_skills()
agent_executor = create_react_agent(llm, tools, checkpointer=memory, prompt=system_prompt)


class ChatRequest(BaseModel):
    message: str
    thread_id: str


@app.get("/api/history/{thread_id}")
def get_history(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    try:
        state = agent_executor.get_state(config)
        if not state or not hasattr(state, 'values') or "messages" not in state.values:
            return {"messages": []}

        history = []
        for msg in state.values["messages"]:
            if isinstance(msg, HumanMessage):
                history.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage) and msg.content:
                if isinstance(msg.content, str):
                    history.append({"role": "ai", "content": msg.content})
                elif isinstance(msg.content, list):
                    text = "".join(item["text"] for item in msg.content if item.get("type") == "text")
                    if text:
                        history.append({"role": "ai", "content": text})

        return {"messages": history}
    except Exception as e:
        return {"messages": []}


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    def event_generator():
        config = {"configurable": {"thread_id": request.thread_id}}
        messages = {"messages": [HumanMessage(content=request.message)]}

        try:
            for event in agent_executor.stream(messages, config, stream_mode="messages"):
                # 【核心修复】：兼容各种新老版本的 LangGraph 数据结构
                chunk = event[0] if isinstance(event, tuple) else event

                if hasattr(chunk, "type") and chunk.type == "ai":
                    # 拦截工具调用
                    if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                        for tc in chunk.tool_calls:
                            yield f"data: {json.dumps({'type': 'tool', 'name': tc['name'], 'args': tc['args']})}\n\n"

                    # 拦截正文内容
                    if chunk.content:
                        if isinstance(chunk.content, str):
                            yield f"data: {json.dumps({'type': 'content', 'chunk': chunk.content})}\n\n"
                        elif isinstance(chunk.content, list):
                            for item in chunk.content:
                                if item.get("type") == "text" and item.get("text"):
                                    yield f"data: {json.dumps({'type': 'content', 'chunk': item['text']})}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            # 捕获报错并推给前端
            traceback.print_exc()
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")