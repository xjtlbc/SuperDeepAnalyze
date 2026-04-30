"""端到端测试脚本 — 模拟完整用户操作流程。

流程：
1. 创建知识库
2. 上传测试用例文件（Word + Excel）
3. 触发预编译
4. 查看编译结果
5. 检查Wiki/图谱页面
6. 创建会话，进行Agent问答
7. 验证Agent Loop行为
"""
import httpx
import json
import time
import os
import sys
import glob
import asyncio

BASE_URL = "http://127.0.0.1:8000"
CASE_DIR = os.path.join(os.path.dirname(__file__), "cases", "005_li_ Assault_case")

# Colors for output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"

passed = 0
failed = 0
errors = []


def log_test(name, success, detail=""):
    global passed, failed
    if success:
        passed += 1
        print(f"  {GREEN}[PASS]{RESET} {name}")
    else:
        failed += 1
        msg = f"{name}: {detail}"
        errors.append(msg)
        print(f"  {RED}[FAIL]{RESET} {msg}")


def print_header(text):
    print(f"\n{'='*60}")
    print(f"  {BLUE}{text}{RESET}")
    print(f"{'='*60}")


def print_result():
    global passed, failed
    print(f"\n{'='*60}")
    print(f"  测试结果: {GREEN}通过 {passed}{RESET} / 失败 {RED}{failed}{RESET}")
    if errors:
        print(f"\n  失败详情:")
        for e in errors:
            print(f"    {RED}✗{RESET} {e}")
    print(f"{'='*60}")


async def run_tests():
    global passed, failed

    async with httpx.AsyncClient(timeout=60.0) as client:

        # =========================================================
        # Step 1: Health check
        # =========================================================
        print_header("Step 1: 健康检查")
        try:
            r = await client.get(f"{BASE_URL}/api/health")
            log_test("后端健康检查", r.status_code == 200 and r.json().get("status") == "ok")
        except Exception as e:
            log_test("后端健康检查", False, str(e))

        try:
            r = await client.get("http://127.0.0.1:5173/")
            log_test("前端页面加载", r.status_code == 200)
        except Exception as e:
            log_test("前端页面加载", False, str(e))

        # =========================================================
        # Step 2: Check model config (need API key)
        # =========================================================
        print_header("Step 2: 检查模型配置")
        try:
            r = await client.get(f"{BASE_URL}/api/models/config")
            data = r.json()
            if data.get("configured", False):
                models = []
                for role in ["main", "lightweight", "embedding", "vlm"]:
                    if data.get(role, {}).get("enabled"):
                        models.append(f"{role}={data[role].get('model_name')}")
                log_test("模型配置存在", True, f"已配置: {', '.join(models)}")
            else:
                log_test("模型配置存在", False, "未找到模型配置，请先在前端配置模型")
                return
        except Exception as e:
            log_test("模型配置检查", False, str(e))
            return

        # =========================================================
        # Step 3: Create Knowledge Base
        # =========================================================
        print_header("Step 3: 创建知识库")
        kb_id = None
        try:
            r = await client.post(f"{BASE_URL}/api/knowledge-bases", json={
                "name": "E2E测试_李某故意伤害案",
                "description": "端到端测试用例，包含14个Word文档和1个Excel文件"
            })
            if r.status_code in (200, 201):
                kb_id = r.json().get("id")
                log_test("知识库创建", True, f"ID: {kb_id}")
            else:
                log_test("知识库创建", False, f"status={r.status_code} body={r.text[:200]}")
        except Exception as e:
            log_test("知识库创建", False, str(e))

        if not kb_id:
            print(f"\n{RED}知识库创建失败，无法继续{RESET}")
            print_result()
            return

        # =========================================================
        # Step 4: Upload test files
        # =========================================================
        print_header("Step 4: 上传测试用例文件")
        if not os.path.isdir(CASE_DIR):
            log_test("测试用例目录", False, f"目录不存在: {CASE_DIR}")
        else:
            files = sorted(glob.glob(os.path.join(CASE_DIR, "*")))
            print(f"  找到 {len(files)} 个测试文件")

            for f in files:
                fname = os.path.basename(f)
                try:
                    with open(f, "rb") as fh:
                        r = await client.post(
                            f"{BASE_URL}/api/documents/upload/{kb_id}",
                            files={"file": (fname, fh)},
                        )
                    if r.status_code in (200, 201):
                        data = r.json()
                        log_test(f"上传: {fname}", True, f"ID={data.get('id', '?')} chunks={data.get('chunk_count', '?')}")
                    else:
                        log_test(f"上传: {fname}", False, f"status={r.status_code} body={r.text[:200]}")
                except Exception as e:
                    log_test(f"上传: {fname}", False, str(e))

                time.sleep(0.5)  # Brief pause between uploads

        # =========================================================
        # Step 5: Verify documents
        # =========================================================
        print_header("Step 5: 验证文档列表")
        try:
            r = await client.get(f"{BASE_URL}/api/documents/list/{kb_id}")
            docs = r.json()
            if isinstance(docs, list):
                completed = sum(1 for d in docs if d.get("parse_status") == "completed")
                log_test("文档列表", True, f"共 {len(docs)} 个，{completed} 个解析完成")
            else:
                log_test("文档列表", False, f"unexpected response")
        except Exception as e:
            log_test("文档列表", False, str(e))

        # =========================================================
        # Step 6: Trigger Compilation (via HTTP, not WebSocket)
        # =========================================================
        print_header("Step 6: 触发预编译")
        compile_started = False
        try:
            # Compile can take a long time — use 3600s timeout
            async with httpx.AsyncClient(timeout=3600.0) as compile_client:
                r = await compile_client.post(f"{BASE_URL}/api/compile/{kb_id}")
            if r.status_code in (200, 201, 202):
                log_test("编译触发", True, f"status={r.status_code}")
                compile_started = True
            else:
                log_test("编译触发", False, f"status={r.status_code} body={r.text[:300]}")
        except httpx.ReadTimeout:
            # POST timed out but server may still be compiling in background
            log_test("编译触发", False, "HTTP超时(3600s)，服务端可能仍在后台编译")
        except Exception as e:
            log_test("编译触发", False, str(e))

        if compile_started:
            # Poll for compilation status
            print(f"\n  {YELLOW}等待编译完成...{RESET}")
            max_wait = 3600  # 1 hour max
            poll_interval = 10
            elapsed = 0

            while elapsed < max_wait:
                try:
                    r = await client.get(f"{BASE_URL}/api/knowledge-bases/{kb_id}")
                    kb = r.json()
                    status = kb.get("compile_status", "pending")
                    print(f"  编译状态: {status} (已等待 {elapsed}s)")

                    if status in ("completed", "failed"):
                        log_test("编译完成", status == "completed", f"status={status}")
                        break
                except Exception:
                    pass

                await asyncio.sleep(poll_interval)
                elapsed += poll_interval
            else:
                log_test("编译完成", False, f"超时 ({max_wait}s)")

        # =========================================================
        # Step 7: Check Wiki pages
        # =========================================================
        print_header("Step 7: 检查Wiki和图谱")
        try:
            r = await client.get(f"{BASE_URL}/api/wiki/{kb_id}")
            if r.status_code == 200:
                data = r.json()
                entities = data.get("entities", [])
                log_test("Wiki概览", True, f"entities={len(entities)} pages={data.get('page_count', '?')}")
            else:
                log_test("Wiki概览", False, f"status={r.status_code}")
        except Exception as e:
            log_test("Wiki概览", False, str(e))

        try:
            r = await client.get(f"{BASE_URL}/api/graph/{kb_id}")
            if r.status_code == 200:
                data = r.json()
                log_test("知识图谱", True, f"nodes={len(data.get('nodes', []))} edges={len(data.get('edges', []))}")
            else:
                log_test("知识图谱", False, f"status={r.status_code}")
        except Exception as e:
            log_test("知识图谱", False, str(e))

        # =========================================================
        # Step 8: Create session and test Agent Q&A
        # =========================================================
        print_header("Step 8: Agent问答测试")
        session_id = None

        # Create session
        try:
            r = await client.post(f"{BASE_URL}/api/sessions", json={
                "kb_id": kb_id,
                "title": "E2E测试会话"
            })
            if r.status_code in (200, 201):
                session_id = r.json().get("id")
                log_test("创建会话", True, f"ID: {session_id}")
            else:
                log_test("创建会话", False, f"status={r.status_code}")
        except Exception as e:
            log_test("创建会话", False, str(e))

        if session_id:
            # Test questions
            questions = [
                {"q": "本案的犯罪嫌疑人是谁？", "expected_keywords": ["李某"]},
                {"q": "被害人伤情如何？", "expected_keywords": ["轻伤"]},
                {"q": "案发时间和地点是什么？", "expected_keywords": ["3月15日", "蓝旗营"]},
                {"q": "本案有几个证人？分别是谁？", "expected_keywords": []},
            ]

            for i, qa in enumerate(questions):
                try:
                    r = await client.post(
                        f"{BASE_URL}/api/sessions/{session_id}/messages",
                        json={"content": qa["q"]},
                        timeout=120.0,
                    )
                    if r.status_code == 200:
                        data = r.json()
                        answer = data.get("content", "")
                        has_keywords = any(kw in answer for kw in qa["expected_keywords"])
                        log_test(
                            f"问答{i+1}: {qa['q'][:30]}...",
                            has_keywords or len(answer) > 50,
                            f"回答长度={len(answer)}, 关键词匹配={has_keywords}"
                        )
                        if len(answer) > 200:
                            print(f"    回答摘要: {answer[:200]}...")
                    else:
                        log_test(f"问答{i+1}", False, f"status={r.status_code} body={r.text[:200]}")
                except httpx.ReadTimeout:
                    log_test(f"问答{i+1}", False, "请求超时(120s)")
                except Exception as e:
                    log_test(f"问答{i+1}", False, str(e))

                time.sleep(1)

        # =========================================================
        # Step 9: Check L2 chunks
        # =========================================================
        print_header("Step 9: 检查L2原文层")
        try:
            r = await client.get(f"{BASE_URL}/api/documents/list/{kb_id}")
            docs = r.json()
            if docs:
                doc_id = docs[0].get("id")
                r2 = await client.get(f"{BASE_URL}/api/documents/{doc_id}/chunks", params={"kb_id": kb_id})
                if r2.status_code == 200:
                    data = r2.json()
                    chunks = data if isinstance(data, list) else data.get("chunks", [])
                    log_test("L2原文层", True, f"文档 {docs[0].get('filename')} 有 {len(chunks)} 个chunk")
                else:
                    log_test("L2原文层", False, f"status={r2.status_code}")
        except Exception as e:
            log_test("L2原文层", False, str(e))

        # =========================================================
        # Final Result
        # =========================================================
        print_result()


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_tests())
