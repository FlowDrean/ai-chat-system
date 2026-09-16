"""AI Chat Assistant —— 后端应用包。

模块划分（详见 docs/架构说明.md）：

    app.api          路由层（只做参数校验 / 鉴权 / 调用 service）
    app.services     业务逻辑层（编排、事务边界）
    app.repositories 数据访问层（SQLAlchemy 2.x async ORM）
    app.llm          LLM / Embedding 工厂，屏蔽各家供应商差异
    app.rag          文档加载、切分、检索、RAG Pipeline
    app.graph        LangGraph 工作流（意图路由 / RAG / 生成）
"""

__version__ = "1.0.0"
