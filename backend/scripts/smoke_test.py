"""端到端自检脚本。

覆盖开发文档 §55「验收标准」的全部主链路：

    登录 → 模型管理 → （非流式 / SSE 流式）AI 对话 → 知识库 → 上传文档(PDF/CSV/TXT)
        → 解析 + 切分 + Embedding + 向量入库 → 检索测试 → RAG 问答 + 引用来源
        → 会话 / 消息 → Dashboard 统计

用法（需先启动后端）：

    python scripts/smoke_test.py
    python scripts/smoke_test.py --base-url http://127.0.0.1:8000/api \
        --username admin --password admin123456
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx

PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  [PASS] {name} {detail}")
    else:
        FAILED += 1
        print(f"  [FAIL] {name} {detail}")


def make_pdf(path: Path, pages: list[str]) -> None:
    """生成一个最小可用的 PDF（无需第三方库），用于验证 PDF 解析链路。"""
    objs: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{4 + i * 2} 0 R" for i in range(len(pages)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode())
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for i, text in enumerate(pages):
        content_obj = 4 + i * 2 + 1
        objs.append(
            (
                "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>"
            ).encode()
        )
        stream = f"BT /F1 12 Tf 72 760 Td 16 TL ({text}) Tj ET".encode()
        objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for idx, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{idx} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123456")
    parser.add_argument("--wait-seconds", type=int, default=60, help="等待文档向量化的最长时间")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    tmp_dir = Path("storage/uploads")

    async with httpx.AsyncClient(timeout=120.0) as client:
        # ------------------------------------------------------------- 健康检查
        print("\n[1] 健康检查")
        resp = await client.get(f"{base}/health")
        check("GET /api/health", resp.status_code == 200 and resp.json()["code"] == 0)

        # ------------------------------------------------------------- 登录
        print("\n[2] 认证")
        resp = await client.post(
            f"{base}/auth/login", json={"username": args.username, "password": args.password}
        )
        body = resp.json()
        if resp.status_code != 200 or body.get("code") != 0:
            print(f"  登录失败：{body}")
            return 1
        token = body["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        check("POST /api/auth/login", True, f"用户={body['data']['user']['username']}")
        resp = await client.get(f"{base}/auth/me", headers=headers)
        check("GET /api/auth/me", resp.json()["data"]["username"] == args.username)

        # ------------------------------------------------------------- 模型
        print("\n[3] 模型管理")
        resp = await client.get(f"{base}/models", headers=headers)
        models = resp.json()["data"]["items"]
        check("GET /api/models", len(models) >= 1, f"共 {len(models)} 个模型")
        default_model = next((m for m in models if m["is_default"]), models[0])
        default_model_id = default_model["id"]
        # 自检统一使用内置 mock 模型：避免消耗使用者的真实 API 额度，结果也稳定可复现
        mock_model = next((m for m in models if m["provider"] == "mock" and m["enabled"]), None)
        chat_model_id = mock_model["id"] if mock_model else default_model_id
        check("模型 API Key 脱敏", "api_key" not in default_model, "响应中不含明文字段")

        resp = await client.post(f"{base}/models", headers=headers, json={
            "name": "自检-DeepSeek",
            "provider": "deepseek",
            "model_name": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": "sk-selftest0123456789abcdef",
            "temperature": 0.7,
            "max_tokens": 2048,
            "enabled": True,
        })
        created = resp.json()
        check("POST /api/models", created.get("code") == 0)
        new_model_id = created["data"]["id"] if created.get("code") == 0 else None
        if new_model_id:
            check(
                "API Key 已加密 + 脱敏返回",
                "sk-selftest0123456789abcdef" != (created["data"].get("api_key_masked") or ""),
                f"masked={created['data'].get('api_key_masked')}",
            )
            # 数据库里必须是密文
            resp = await client.get(f"{base}/models/{new_model_id}", headers=headers)
            mask = resp.json()["data"]["api_key_masked"] or ""
            check("再次读取仍为脱敏值", "*" in mask or "•" in mask, mask)

        providers = await client.get(f"{base}/models/providers", headers=headers)
        check("GET /api/models/providers", len(providers.json()["data"]) >= 10)

        # ------------------------------------------------------------- 非流式聊天
        print("\n[4] AI 聊天（非流式）")
        resp = await client.post(f"{base}/chat", headers=headers, json={
            "content": "请用三句话介绍 FastAPI",
        "model_id": chat_model_id,
            "stream": False,
        })
        chat = resp.json()
        check("POST /api/chat", chat.get("code") == 0)
        conversation_id = chat["data"]["conversation_id"] if chat.get("code") == 0 else None
        if conversation_id:
            check("助手回复非空", bool(chat["data"]["message"]["content"]))
            check("Token 统计已记录", chat["data"]["message"]["total_tokens"] > 0,
                  f"tokens={chat['data']['message']['total_tokens']}, latency={chat['data']['message']['latency_ms']}ms")

        # ------------------------------------------------------------- SSE 流式聊天
        print("\n[5] AI 聊天（SSE 流式）")
        tokens: list[str] = []
        event_types: list[str] = []
        async with client.stream(
            "POST",
            f"{base}/chat/stream",
            headers=headers,
            json={"content": "写一个 Python 的 Hello World，并给出代码块",
                  "model_id": chat_model_id, "conversation_id": conversation_id},
        ) as response:
            check("SSE Content-Type", response.headers.get("content-type", "").startswith("text/event-stream"))
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                event_types.append(event["type"])
                if event["type"] == "token":
                    tokens.append(event["content"])
                if event["type"] == "done":
                    break

        streamed = "".join(tokens)
        check("SSE 收到 start/meta/token/done", {"start", "meta", "token", "done"} <= set(event_types),
              f"事件={sorted(set(event_types))}")
        check("流式 token 数量 > 1（真流式）", len(tokens) > 1, f"{len(tokens)} 个片段")
        check("流式内容非空", len(streamed) > 20, f"{len(streamed)} 字符")

        # ------------------------------------------------------------- 会话与消息
        print("\n[6] 会话与消息")
        resp = await client.get(f"{base}/conversations", headers=headers)
        conversations = resp.json()["data"]["items"]
        check("GET /api/conversations", len(conversations) >= 1, f"{len(conversations)} 个会话")
        resp = await client.get(f"{base}/conversations/{conversation_id}/messages", headers=headers)
        messages = resp.json()["data"]
        check("GET /api/conversations/{id}/messages", len(messages) >= 4, f"{len(messages)} 条消息")
        check("会话标题自动生成", any(c["title"] != "新对话" for c in conversations))

        resp = await client.put(f"{base}/conversations/{conversation_id}", headers=headers,
                                json={"title": "自检会话-已重命名", "is_favorite": True})
        check("PUT /api/conversations/{id}", resp.json()["data"]["title"] == "自检会话-已重命名")

        # ------------------------------------------------------------- 知识库
        print("\n[7] 知识库与文档")
        resp = await client.post(f"{base}/knowledge-bases", headers=headers, json={
            "name": "自检知识库",
            "description": "smoke test 自动创建",
            "embedding_provider": "local",
            "embedding_model": "local-hash-512",
            "embedding_dimension": 512,
            "chunk_size": 300,
            "chunk_overlap": 50,
            "top_k": 3,
            "similarity_threshold": 0.05,
        })
        kb = resp.json()
        check("POST /api/knowledge-bases", kb.get("code") == 0, kb.get("message", ""))
        kb_id = kb["data"]["id"]

        # 准备测试文件
        tmp_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = tmp_dir / "_selftest_fastapi.pdf"
        make_pdf(pdf_path, [
            "FastAPI is a modern, high performance Python web framework for building APIs. "
            "It is based on Starlette for the web parts and Pydantic for the data parts.",
            "FastAPI supports asynchronous request handlers with async def, automatic OpenAPI "
            "documentation, dependency injection and Pydantic based data validation.",
        ])
        csv_path = tmp_dir / "_selftest_langchain.csv"
        csv_path.write_text(
            "topic,description\n"
            "RAG,RAG 是检索增强生成它结合向量检索与大模型生成\n"
            "Embedding,Embedding 把文本映射为向量用于相似度检索\n"
            "VectorStore,向量库用于存储和检索向量常见有 Chroma 与 Milvus\n"
            "LangGraph,LangGraph 用于构建有状态的多步骤 AI 工作流\n",
            encoding="utf-8",
        )
        txt_path = tmp_dir / "_selftest_notes.txt"
        txt_path.write_text(
            "知识库检索流程说明：\n"
            "1. 用户问题先做 Query Embedding\n"
            "2. 在向量库中执行相似度检索得到 Top K 文档\n"
            "3. 把检索结果拼接成上下文交给大模型生成答案\n"
            "4. 回答中必须标注引用来源，避免编造内容\n",
            encoding="utf-8",
        )

        uploaded: list[int] = []
        for path, mime in (
            (pdf_path, "application/pdf"),
            (csv_path, "text/csv"),
            (txt_path, "text/plain"),
        ):
            with path.open("rb") as fp:
                resp = await client.post(
                    f"{base}/knowledge-bases/{kb_id}/documents",
                    headers=headers,
                    files={"file": (path.name, fp, mime)},
                )
            body = resp.json()
            ok = body.get("code") == 0
            check(f"上传 {path.suffix} 文档", ok, body.get("message", "") if not ok else "")
            if ok:
                uploaded.append(body["data"]["id"])

        # 等待后台向量化完成
        print("    等待文档解析 / 向量化 ...")
        deadline = time.time() + args.wait_seconds
        processed: dict[int, dict] = {}
        while time.time() < deadline:
            resp = await client.get(f"{base}/knowledge-bases/{kb_id}/documents?page_size=50", headers=headers)
            processed = {d["id"]: d for d in resp.json()["data"]["items"]}
            if all(processed.get(doc_id, {}).get("status") in ("completed", "failed") for doc_id in uploaded):
                break
            await asyncio.sleep(1.5)

        for doc_id in uploaded:
            doc = processed.get(doc_id, {})
            check(
                f"文档 {doc_id} 向量化完成",
                doc.get("status") == "completed",
                f"status={doc.get('status')} chunks={doc.get('chunk_count')} err={doc.get('error_message')}",
            )

        resp = await client.get(f"{base}/knowledge-bases/{kb_id}", headers=headers)
        detail = resp.json()["data"]
        check("知识库统计已更新", detail["chunk_count"] > 0, f"chunks={detail['chunk_count']}, docs={detail['document_count']}")
        check("文档出参不含服务器路径", "file_path" not in json.dumps(detail, ensure_ascii=False))

        # ------------------------------------------------------------- 检索测试
        print("\n[8] RAG 检索")
        resp = await client.post(f"{base}/knowledge-bases/{kb_id}/retrieval-test", headers=headers,
                                 json={"query": "FastAPI 是异步的吗？", "top_k": 3})
        retrieval = resp.json()
        check("POST /api/knowledge-bases/{id}/retrieval-test", retrieval.get("code") == 0)
        hits = retrieval["data"]["chunks"] if retrieval.get("code") == 0 else []
        check("检索命中结果", len(hits) > 0, f"命中 {len(hits)} 条，latency={retrieval['data']['latency_ms']}ms")
        if hits:
            check("命中结果含来源文件名与相似度", bool(hits[0].get("filename")) and hits[0]["score"] > 0,
                  f"{hits[0].get('filename')} score={hits[0]['score']}")

        # ------------------------------------------------------------- RAG 问答
        print("\n[9] RAG 问答（带引用来源）")
        sources: list[dict] = []
        answer_tokens: list[str] = []
        async with client.stream(
            "POST",
            f"{base}/chat/stream",
            headers=headers,
            json={
                "content": "根据知识库说明 RAG 的检索流程是什么？",
        "model_id": chat_model_id,
                "knowledge_base_id": kb_id,
                "use_rag": True,
            },
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event["type"] == "token":
                    answer_tokens.append(event["content"])
                elif event["type"] == "sources":
                    sources = event.get("sources") or []
                elif event["type"] == "done":
                    rag_message = event.get("message") or {}
                    break

        check("RAG 返回引用来源", len(sources) > 0, f"{len(sources)} 个来源")
        check("引用来源包含文件名 / 相似度", bool(sources) and bool(sources[0].get("filename")) and sources[0]["score"] > 0,
              f"{sources[0]['filename'] if sources else '-'} score={sources[0]['score'] if sources else '-'}")
        check("RAG 回答已落库（含 sources）", bool(rag_message.get("sources")))
        check("RAG 回答内容非空", len("".join(answer_tokens)) > 10)

        # ------------------------------------------------------------- Prompt
        print("\n[10] Prompt 管理")
        resp = await client.get(f"{base}/prompts", headers=headers)
        prompts = resp.json()["data"]["items"]
        check("GET /api/prompts（含内置模板）", len(prompts) >= 5, f"{len(prompts)} 个")
        resp = await client.post(f"{base}/prompts", headers=headers, json={
            "name": "自检 Prompt",
            "content": "你是测试助手。用户问题：{{question}}",
            "scene": "system",
            "tags": ["自检"],
        })
        prompt = resp.json()
        check("POST /api/prompts", prompt.get("code") == 0)
        if prompt.get("code") == 0:
            check("变量自动提取", "question" in (prompt["data"]["variables"] or []), str(prompt["data"]["variables"]))
            resp = await client.post(f"{base}/prompts/{prompt['data']['id']}/render", headers=headers,
                                     json={"variables": {"question": "你好"}})
            check("POST /api/prompts/{id}/render", "你好" in resp.json()["data"]["content"])
            await client.delete(f"{base}/prompts/{prompt['data']['id']}", headers=headers)

        # ------------------------------------------------------------- Dashboard
        print("\n[11] Dashboard 与统计")
        resp = await client.get(f"{base}/dashboard?days=7", headers=headers)
        dash = resp.json()
        check("GET /api/dashboard", dash.get("code") == 0)
        stats = dash["data"]["stats"]
        check("统计：今日对话数 > 0", stats["today_conversations"] >= 1, str(stats["today_conversations"]))
        check("统计：Token 消耗 > 0", stats["today_tokens"] > 0, str(stats["today_tokens"]))
        check("统计：趋势数据", len(dash["data"]["trends"]) == 7, f"{len(dash['data']['trends'])} 天")
        check("统计：模型分布", len(dash["data"]["model_usage"]) >= 1)
        check("统计：知识库分布", len(dash["data"]["knowledge_usage"]) >= 1)

        # ------------------------------------------------------------- 权限
        print("\n[12] 权限与异常处理")
        resp = await client.post(f"{base}/users", headers=headers, json={
            "username": "selftest_user", "password": "test123456", "role": "user",
        })
        check("POST /api/users（管理员）", resp.json().get("code") == 0)
        new_user_id = resp.json()["data"]["id"] if resp.json().get("code") == 0 else None
        if new_user_id:
            resp = await client.post(f"{base}/auth/login", json={"username": "selftest_user", "password": "test123456"})
            user_token = resp.json()["data"]["access_token"]
            user_headers = {"Authorization": f"Bearer {user_token}"}
            resp = await client.post(f"{base}/models", headers=user_headers, json={
                "name": "越权模型", "provider": "openai", "model_name": "gpt-4o", "api_key": "sk-x",
            })
            check("普通用户访问模型管理被拒绝（403）", resp.status_code == 403 or resp.json().get("code") == 40300,
                  f"HTTP {resp.status_code} code={resp.json().get('code')}")

        resp = await client.get(f"{base}/conversations")
        check("未登录访问被拒绝（401）", resp.status_code == 401 or resp.json().get("code") == 40100,
              f"HTTP {resp.status_code}")

        resp = await client.post(f"{base}/chat", headers=headers, json={"content": "", "stream": False})
        check("空消息被参数校验拦截", resp.status_code == 422, f"HTTP {resp.status_code}")

        resp = await client.get(f"{base}/models/999999", headers=headers)
        check("不存在的模型返回 404", resp.status_code == 404, f"HTTP {resp.status_code}")

        # ------------------------------------------------------------- 模型连通性测试
        print("\n[13] 模型连接测试")
        resp = await client.post(f"{base}/models/{default_model['id']}/test", headers=headers)
        test_result = resp.json()
        check(
            "POST /api/models/{id}/test（mock 模型）",
            test_result.get("code") == 0 and test_result["data"]["success"],
            test_result["data"]["message"] if test_result.get("code") == 0 else test_result.get("message"),
        )

        # ------------------------------------------------------------- 停止生成
        print("\n[14] 停止生成（客户端中断  保存已生成内容）")
        target_conversation = None
        async with client.stream(
            "POST",
            f"{base}/chat/stream",
            headers=headers,
            json={"content": "请详细介绍一下 FastAPI 的依赖注入机制", "model_id": chat_model_id, "stream": True},
        ) as response:
            received = 0
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event["type"] == "meta":
                    target_conversation = event["conversation"]["id"]
                if event["type"] == "token":
                    received += 1
                    if received >= 3:
                        break  # 主动断开连接，模拟点击「停止生成」
        check("中断流式连接", received >= 3, f"已接收 {received} 个 token")

        await asyncio.sleep(2)
        resp = await client.get(f"{base}/conversations/{target_conversation}/messages", headers=headers)
        stopped_messages = [m for m in resp.json()["data"] if m["role"] == "assistant"]
        last = stopped_messages[-1] if stopped_messages else {}
        check(
            "中断后仍保存了已生成内容",
            last.get("status") == "stopped" and bool(last.get("content")),
            f"status={last.get('status')} chars={len(last.get('content') or '')}",
        )

        # ------------------------------------------------------------- 重新生成
        print("\n[15] 重新生成")
        resp = await client.get(f"{base}/conversations/{target_conversation}/messages", headers=headers)
        before_messages = resp.json()["data"]
        last_user = [m for m in before_messages if m["role"] == "user"][-1]
        async with client.stream(
            "POST",
            f"{base}/chat/stream",
            headers=headers,
            json={"content": last_user["content"], "conversation_id": target_conversation,
                      "model_id": chat_model_id, "regenerate": True},
        ) as response:
            done_event = None
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                if event["type"] == "done":
                    done_event = event
                    break
        check("regenerate=true 流式重生成成功", bool(done_event and done_event.get("message", {}).get("content")))

        resp = await client.get(f"{base}/conversations/{target_conversation}/messages", headers=headers)
        after_messages = resp.json()["data"]
        check(
            "重新生成未重复追加用户消息",
            len([m for m in after_messages if m["role"] == "user"])
            == len([m for m in before_messages if m["role"] == "user"]),
            f"users: {len([m for m in before_messages if m['role'] == 'user'])}  "
            f"{len([m for m in after_messages if m['role'] == 'user'])}",
        )

        # ------------------------------------------------------------- 清空会话
        resp = await client.post(f"{base}/conversations/{target_conversation}/clear", headers=headers)
        check("POST /conversations/{id}/clear", resp.json()["data"]["message_count"] == 0)
        resp = await client.get(f"{base}/conversations/{target_conversation}/messages", headers=headers)
        check("清空后消息列表为空", len(resp.json()["data"]) == 0)
        await client.delete(f"{base}/conversations/{target_conversation}", headers=headers)

        # ------------------------------------------------------------- 技能
        print("\n[16] 技能（Skills）")
        resp = await client.get(f"{base}/skills", headers=headers)
        skill_list = resp.json()
        check("GET /api/skills（管理列表）", skill_list.get("code") == 0)
        skills = skill_list["data"]["items"] if skill_list.get("code") == 0 else []
        builtin_types = {item["type"] for item in skills}
        check("内置技能已初始化", {"calculator", "current_time", "web_search", "web_fetch"} <= builtin_types,
              f"{len(skills)} 个技能")

        resp = await client.get(f"{base}/skills/specs", headers=headers)
        specs = resp.json()["data"]
        check("GET /api/skills/specs（动态表单规格）", len(specs) >= 5, f"{len(specs)} 种类型")
        http_spec = next((item for item in specs if item["type"] == "http_request"), None)
        check("自定义 HTTP 技能支持动态入参", bool(http_spec and http_spec["uses_dynamic_args"]))

        resp = await client.get(f"{base}/skills/available", headers=headers)
        available = resp.json()["data"]
        check("GET /api/skills/available（聊天可用）", all(item["configured"] for item in available),
              f"{len(available)} 个可用")

        calc_skill = next((item for item in skills if item["type"] == "calculator"), None)
        if calc_skill:
            resp = await client.post(f"{base}/skills/{calc_skill['id']}/test", headers=headers,
                                     json={"arguments": {"expression": "(88+12)/4*3"}})
            result = resp.json()["data"]
            check("POST /api/skills/{id}/test（计算器试运行）", result["success"] and "75" in result["output"],
                  result["output"])

        # 自定义技能：新建  试运行  删除
        resp = await client.post(f"{base}/skills", headers=headers, json={
            "name": "自检-HTTP接口", "type": "http_request", "enabled": True, "visible_to_users": True,
            "description": "自检用接口", "config": {
                "url": "http://127.0.0.1:9/ping", "method": "GET", "params_in": "query",
                "args_schema": '{"keyword": {"type": "string", "description": "查询词"}}', "headers": "{}"}},
        )
        created_skill = resp.json()
        check("POST /api/skills（新建自定义技能）", created_skill.get("code") == 0, created_skill.get("message", ""))
        custom_skill_id = created_skill["data"]["id"] if created_skill.get("code") == 0 else None
        if custom_skill_id:
            resp = await client.post(f"{base}/skills/{custom_skill_id}/test", headers=headers,
                                     json={"arguments": {"keyword": "hello"}})
            check("自定义技能试运行返回可读错误", resp.json()["data"]["error"] is not None,
                  (resp.json()["data"]["error"] or "")[:60])
            resp = await client.delete(f"{base}/skills/{custom_skill_id}", headers=headers)
            check("DELETE /api/skills/{id}", resp.json().get("code") == 0)

        # 带技能聊天（mock 模型会触发计算器）
        print("\n[17] 带技能的对话（Tool Calling）")
        if calc_skill:
            resp = await client.post(f"{base}/chat", headers=headers, json={
                "content": "帮我计算 (88+12)/4*3 等于多少",
                "model_id": default_model_id,
                "skill_ids": [calc_skill["id"]],
                "stream": False,
            })
            body = resp.json()
            check("POST /api/chat 带技能", body.get("code") == 0)
            message = body["data"]["message"] if body.get("code") == 0 else {}
            used = message.get("skills") or []
            check("回答中记录了技能调用", len(used) == 1 and used[0]["status"] == "ok",
                  f"{[(item['name'], item['arguments']) for item in used]}")
            check("技能结果参与最终回答", "75" in (message.get("content") or ""))

        # 流式技能事件
        if calc_skill:
            event_types: list[str] = []
            skill_phases: list[str] = []
            async with client.stream(
                "POST",
                f"{base}/chat/stream",
                headers=headers,
                json={"content": "帮我算 45*2+10", "model_id": default_model_id,
                      "skill_ids": [calc_skill["id"]]},
            ) as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    event_types.append(event["type"])
                    if event["type"] == "skill":
                        skill_phases.append(str(event.get("phase")))
                    if event["type"] == "done":
                        done_event = event
                        break
            check("流式返回 skill 事件", {"planned", "call", "result"} <= set(skill_phases), str(skill_phases))
            check("done 事件包含技能记录", bool(done_event.get("skills")), str(len(done_event.get("skills") or [])))

        # ------------------------------------------------------------- MCP
        print("\n[18] MCP（Model Context Protocol）")
        resp = await client.get(f"{base}/mcp/transports", headers=headers)
        transports = resp.json()["data"]
        check("GET /api/mcp/transports", len(transports) == 3,
              ", ".join(item["value"] for item in transports))

        resp = await client.post(f"{base}/mcp/servers", headers=headers, json={
            "name": "自检-MCP演示服务",
            "transport": "stdio",
            "command": sys.executable,
            "args": ["scripts/demo_mcp_server.py"],
            "cwd": ".",
            "timeout": 60,
            "enabled": True,
            "visible_to_users": True,
            "description": "自检用的本地 MCP 演示服务",
        })
        created_mcp = resp.json()
        check("POST /api/mcp/servers（stdio）", created_mcp.get("code") == 0, created_mcp.get("message", ""))
        mcp_id = created_mcp["data"]["id"] if created_mcp.get("code") == 0 else None

        if mcp_id:
            resp = await client.post(f"{base}/mcp/servers/{mcp_id}/test", headers=headers)
            mcp_test = resp.json()["data"]
            check("连接测试 + 工具发现", mcp_test["success"] and mcp_test["tool_count"] >= 3,
                  f"{mcp_test['tool_count']} 个工具 / {mcp_test['latency_ms']}ms")
            tool_names = {item["name"] for item in mcp_test["tools"]}
            check("发现 add / echo / text_stats", {"add", "echo", "text_stats"} <= tool_names, str(sorted(tool_names)))
            check("工具带 JSON Schema", all(item["input_schema"] for item in mcp_test["tools"]))

            resp = await client.get(f"{base}/mcp/servers/{mcp_id}/tools", headers=headers)
            check("GET /api/mcp/servers/{id}/tools（缓存）", len(resp.json()["data"]) >= 3)

            resp = await client.post(f"{base}/mcp/servers/{mcp_id}/call-tool", headers=headers,
                                     json={"tool_name": "add", "arguments": {"a": 100, "b": 23}})
            called = resp.json()["data"]
            check("调试调用 MCP 工具", called["success"] and "123" in called["output"], called["output"])

            resp = await client.post(f"{base}/mcp/servers/{mcp_id}/call-tool", headers=headers,
                                     json={"tool_name": "not_exist", "arguments": {}})
            check("调用不存在的工具返回可读错误", resp.json()["data"]["is_error"] is True)

            resp = await client.get(f"{base}/mcp/available", headers=headers)
            available_mcp = resp.json()["data"]
            check("GET /api/mcp/available", any(item["id"] == mcp_id for item in available_mcp),
                  f"{len(available_mcp)} 个可用")

            # 带 MCP 工具的对话
            mcp_events: list[str] = []
            mcp_records: list[dict] = []
            async with client.stream(
                "POST",
                f"{base}/chat/stream",
                headers=headers,
                json={"content": "请用 add 工具计算 123+456",
                      "model_id": chat_model_id, "mcp_server_ids": [mcp_id]},
            ) as response:
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    event = json.loads(line[6:])
                    if event["type"] == "skill":
                        mcp_events.append(str(event.get("phase")))
                        if event.get("phase") == "result":
                            check("MCP 事件带 source/server", event.get("source") == "mcp" and bool(event.get("server")),
                                  f"source={event.get('source')} server={event.get('server')}")
                    if event["type"] == "done":
                        mcp_records = event.get("skills") or []
                        mcp_conversation_id = event["conversation"]["id"]
                        break
            check("流式返回 MCP 技能事件", {"planned", "call", "result"} <= set(mcp_events), str(mcp_events))
            check("消息记录标记来源为 mcp", bool(mcp_records) and mcp_records[0].get("source") == "mcp",
                  str([(item.get("name"), item.get("source")) for item in mcp_records]))
            check("MCP 工具结果参与回答", any("579" in (item.get("output") or "") for item in mcp_records),
                  str([(item.get("output") or "")[:40] for item in mcp_records]))

            resp = await client.get(f"{base}/conversations/{mcp_conversation_id}", headers=headers)
            check("会话持久化 mcp_server_ids", resp.json()["data"].get("mcp_server_ids") == [mcp_id],
                  str(resp.json()["data"].get("mcp_server_ids")))

            resp = await client.get(f"{base}/mcp/servers/{mcp_id}", headers=headers)
            check("MCP 服务调用计数", resp.json()["data"]["usage_count"] >= 1,
                  f"usage_count={resp.json()['data']['usage_count']}")

            resp = await client.delete(f"{base}/mcp/servers/{mcp_id}", headers=headers)
            check("DELETE /api/mcp/servers/{id}", resp.json().get("code") == 0)

        # ---- 配置导入 / 导出（Claude Desktop / Cursor 的 mcpServers 格式）----
        amap_config = {
            "mcpServers": {
                "自检导入-amap-maps": {
                    "command": "npx",
                    "args": ["-y", "@amap/amap-maps-mcp-server"],
                    "env": {"AMAP_MAPS_API_KEY": "您在高德官网上申请的key"},
                }
            }
        }
        resp = await client.post(f"{base}/mcp/import", headers=headers,
                                 json={"payload": json.dumps(amap_config, ensure_ascii=False),
                                       "auto_test": False, "strategy": "rename"})
        imported = resp.json()
        check("POST /api/mcp/import（amap 配置）", imported.get("code") == 0, imported.get("message", ""))
        import_items = imported["data"]["items"] if imported.get("code") == 0 else []
        imported_id = import_items[0]["server_id"] if import_items else None
        check("解析 command/args  stdio", bool(import_items) and import_items[0]["transport"] == "stdio",
              import_items[0]["transport"] if import_items else "")

        if imported_id:
            resp = await client.get(f"{base}/mcp/servers/{imported_id}", headers=headers)
            detail = resp.json()["data"]
            check("导入后命令与参数正确",
                  detail["command"] == "npx" and detail["args"] == ["-y", "@amap/amap-maps-mcp-server"],
                  f"{detail['command']} {detail['args']}")
            check("env 明文不外泄（出参脱敏）",
                  "您在高德官网上申请的key" not in json.dumps(detail["env"], ensure_ascii=False)
                  and "AMAP_MAPS_API_KEY" in (detail["env"] or {}),
                  str(detail["env"]))
            check("标记出脱敏字段", "AMAP_MAPS_API_KEY" in (detail.get("masked_keys") or []))

        # 冲突策略
        resp = await client.post(f"{base}/mcp/import", headers=headers,
                                 json={"payload": json.dumps(amap_config, ensure_ascii=False),
                                       "auto_test": False, "strategy": "skip"})
        check("重复导入策略 skip", resp.json()["data"]["items"][0]["action"] == "skipped")
        resp = await client.post(f"{base}/mcp/import", headers=headers,
                                 json={"payload": json.dumps(amap_config, ensure_ascii=False),
                                       "auto_test": False, "strategy": "rename"})
        check("重复导入策略 rename", resp.json()["data"]["items"][0]["action"] == "renamed")
        renamed_id = resp.json()["data"]["items"][0]["server_id"]
        resp = await client.post(f"{base}/mcp/import", headers=headers,
                                 json={"payload": json.dumps(amap_config, ensure_ascii=False),
                                       "auto_test": False, "strategy": "overwrite"})
        check("重复导入策略 overwrite", resp.json()["data"]["items"][0]["action"] == "updated")

        # 自动测试连接（用本地演示服务）
        demo_config = {"servers": {"自检导入-演示服务": {
            "command": sys.executable, "args": ["scripts/demo_mcp_server.py"], "cwd": "."}}}
        resp = await client.post(f"{base}/mcp/import", headers=headers,
                                 json={"payload": json.dumps(demo_config, ensure_ascii=False),
                                       "auto_test": True, "strategy": "rename"})
        demo_item = resp.json()["data"]["items"][0]
        check("导入后自动测试并发现工具", demo_item["tool_count"] >= 3,
              f"{demo_item['tool_count']} 个工具 | {demo_item['message']}")
        demo_import_id = demo_item["server_id"]

        # 非法格式
        resp = await client.post(f"{base}/mcp/import", headers=headers, json={"payload": "{bad json"})
        check("非法 JSON 返回可读错误", resp.json()["code"] == 40000, resp.json()["message"][:50])
        resp = await client.post(f"{base}/mcp/import", headers=headers, json={"payload": '{"foo": 1}'})
        check("无法识别的格式返回可读错误", resp.json()["code"] == 40000, resp.json()["message"][:60])

        # 导出
        resp = await client.get(f"{base}/mcp/export", headers=headers)
        exported = resp.json()["data"]
        check("GET /api/mcp/export（默认脱敏）",
              "mcpServers" in exported["content"] and "您在高德官网上申请的key" not in exported["content"],
              f"{exported['count']} 个服务")
        resp = await client.get(f"{base}/mcp/export?include_secrets=true", headers=headers)
        check("导出可包含明文密钥（加密往返正确）",
              "您在高德官网上申请的key" in resp.json()["data"]["content"])

        # 清理导入产生的服务
        for cleanup_id in [imported_id, renamed_id, demo_import_id]:
            if cleanup_id:
                await client.delete(f"{base}/mcp/servers/{cleanup_id}", headers=headers)
        resp = await client.get(f"{base}/mcp/servers?page_size=100", headers=headers)
        leftovers = [item for item in resp.json()["data"]["items"] if "自检导入" in item["name"]]
        for item in leftovers:
            await client.delete(f"{base}/mcp/servers/{item['id']}", headers=headers)
        check("清理导入的测试服务", True, f"剩余 {len(leftovers)} 个由清理逻辑兜底删除")

        # ------------------------------------------------------------- 清理
        print("\n[19] 清理自检数据")
        if new_user_id:
            await client.delete(f"{base}/users/{new_user_id}", headers=headers)
        for doc_id in uploaded:
            await client.delete(f"{base}/documents/{doc_id}", headers=headers)
        await client.delete(f"{base}/knowledge-bases/{kb_id}", headers=headers)
        await client.delete(f"{base}/conversations/{conversation_id}", headers=headers)
        if new_model_id:
            await client.delete(f"{base}/models/{new_model_id}", headers=headers)
        for path in (pdf_path, csv_path, txt_path):
            path.unlink(missing_ok=True)
        check("清理完成", True)

    print("\n" + "=" * 70)
    print(f"自检结果：通过 {PASSED} 项，失败 {FAILED} 项")
    print("=" * 70)
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
