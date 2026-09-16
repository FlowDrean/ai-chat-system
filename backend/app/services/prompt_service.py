"""Prompt 管理服务。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.models.prompt import Prompt
from app.repositories.prompt_repo import PromptRepository
from app.schemas.prompt import PromptCreate, PromptOut, PromptUpdate

logger = get_logger(__name__)

# 系统内置 Prompt 模板（首次启动时写入）
BUILTIN_PROMPTS: list[dict] = [
    {
        "name": "专业程序员助手",
        "scene": "system",
        "tags": ["编程", "通用"],
        "description": "面向工程实践的编码助手，输出可运行代码并解释细节。",
        "variables": [],
        "content": (
            "你是一名专业的软件工程师。\n\n"
            "你需要：\n"
            "1. 分析用户需求\n"
            "2. 给出合理解决方案\n"
            "3. 提供可运行代码\n"
            "4. 解释代码关键点\n"
            "5. 注意异常处理与边界情况\n\n"
            "回答要求：使用 Markdown，代码块必须标注语言；不确定的地方要明确说明。"
        ),
    },
    {
        "name": "RAG 知识库问答",
        "scene": "rag",
        "tags": ["RAG", "知识库"],
        "description": "严格基于知识库内容回答，并标注引用编号。",
        "variables": ["context", "question"],
        "content": (
            "你是一个专业的 AI 助手。\n\n"
            "请根据提供的知识库内容回答用户问题。\n\n"
            "要求：\n"
            "1. 优先使用知识库内容。\n"
            "2. 如果知识库没有相关信息，不要编造。\n"
            "3. 如果无法从知识库得到答案，需要明确告诉用户。\n"
            "4. 可以结合自己的通用知识辅助回答，但必须区分知识库内容和通用知识。\n"
            "5. 回答应该准确、清晰、结构化，引用时使用 [1]、[2] 标注来源编号。\n\n"
            "知识库内容：\n\n{context}"
        ),
    },
    {
        "name": "简洁问答助手",
        "scene": "system",
        "tags": ["简洁"],
        "description": "直接给结论，适合快速查询。",
        "variables": [],
        "content": "请用最简洁的方式回答用户问题：先给结论，再给必要说明，控制在 200 字以内（代码除外）。",
    },
    {
        "name": "前端 Vue3 专家",
        "scene": "system",
        "tags": ["前端", "Vue"],
        "description": "Vue3 + TypeScript + Ant Design Vue 方向的技术助手。",
        "variables": ["user_name"],
        "content": (
            "你是一名资深前端工程师，精通 Vue 3、TypeScript、Vite、Pinia、Ant Design Vue。\n\n"
            "回答时：\n"
            "1. 使用 <script setup lang=\"ts\"> 语法\n"
            "2. 组件遵循 Composition API 最佳实践\n"
            "3. 指出潜在的性能与可维护性问题\n\n"
            "当前用户：{{user_name}}"
        ),
    },
    {
        "name": "SQL / 数据分析助手",
        "scene": "system",
        "tags": ["数据库", "SQL"],
        "description": "编写与优化 SQL，解释执行计划。",
        "variables": ["question"],
        "content": (
            "你是一名数据库专家，精通 MySQL 8.x。\n\n"
            "请针对用户问题：\n"
            "1. 给出可直接执行的 SQL\n"
            "2. 说明索引使用与可能的性能瓶颈\n"
            "3. 提醒常见陷阱（NULL、隐式类型转换、分页深翻页等）\n\n"
            "用户问题：{question}"
        ),
    },
]


def to_prompt_out(prompt: Prompt) -> PromptOut:
    return PromptOut.model_validate(prompt.to_dict())


class PromptService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.prompts = PromptRepository(session)

    # ------------------------------------------------------------------ #
    async def list_prompts(
        self,
        user_id: int,
        *,
        keyword: str | None = None,
        scene: str | None = None,
        enabled: bool | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[PromptOut], int]:
        items, total = await self.prompts.list_visible(
            user_id,
            keyword=keyword,
            scene=scene,
            enabled=enabled,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return [to_prompt_out(p) for p in items], total

    async def get_prompt(self, prompt_id: int, user_id: int) -> Prompt:
        prompt = await self.prompts.get_visible(prompt_id, user_id)
        if prompt is None:
            raise NotFoundError("Prompt 不存在")
        return prompt

    async def create_prompt(self, data: PromptCreate, user_id: int) -> PromptOut:
        prompt = Prompt(
            user_id=user_id,
            name=data.name.strip(),
            content=data.content,
            description=data.description,
            variables=data.variables or self.extract_variables(data.content),
            tags=data.tags,
            scene=data.scene,
            enabled=data.enabled,
        )
        self.session.add(prompt)
        await self.session.flush()
        logger.info("创建 Prompt id=%s name=%s", prompt.id, prompt.name)
        return to_prompt_out(prompt)

    async def update_prompt(self, prompt_id: int, data: PromptUpdate, user_id: int) -> PromptOut:
        prompt = await self.get_prompt(prompt_id, user_id)
        if prompt.is_builtin and prompt.user_id is None:
            raise PermissionDeniedError("系统内置 Prompt 不可修改，请复制后另存为自定义 Prompt")

        payload = data.model_dump(exclude_unset=True)
        if "content" in payload and not payload.get("variables"):
            payload["variables"] = self.extract_variables(payload["content"])
        for key, value in payload.items():
            setattr(prompt, key, value)
        await self.session.flush()
        return to_prompt_out(prompt)

    async def delete_prompt(self, prompt_id: int, user_id: int) -> None:
        prompt = await self.get_prompt(prompt_id, user_id)
        if prompt.is_builtin and prompt.user_id is None:
            raise PermissionDeniedError("系统内置 Prompt 不可删除")
        await self.prompts.delete(prompt)
        logger.info("删除 Prompt id=%s", prompt_id)

    async def render(self, prompt_id: int, user_id: int, variables: dict) -> dict:
        prompt = await self.get_prompt(prompt_id, user_id)
        prompt.usage_count = (prompt.usage_count or 0) + 1
        await self.session.flush()
        return {
            "id": prompt.id,
            "name": prompt.name,
            "content": prompt.render(**variables),
            "variables": prompt.variables or [],
            "missing": [v for v in (prompt.variables or []) if v not in variables],
        }

    # ------------------------------------------------------------------ #
    @staticmethod
    def extract_variables(content: str) -> list[str]:
        import re

        found = re.findall(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", content)
        found += re.findall(r"(?<!\{)\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}(?!\})", content)
        result: list[str] = []
        for name in found:
            if name not in result:
                result.append(name)
        return result

    async def ensure_builtin_prompts(self) -> None:
        """首次启动时初始化内置 Prompt 模板。"""
        existing = {p.name for p in await self.prompts.list_builtin()}
        created = 0
        for item in BUILTIN_PROMPTS:
            if item["name"] in existing:
                continue
            self.session.add(
                Prompt(
                    user_id=None,
                    name=item["name"],
                    content=item["content"],
                    description=item["description"],
                    variables=item["variables"],
                    tags=item["tags"],
                    scene=item["scene"],
                    enabled=True,
                    is_builtin=True,
                )
            )
            created += 1
        if created:
            await self.session.flush()
            logger.info("初始化内置 Prompt 模板 %s 个", created)
