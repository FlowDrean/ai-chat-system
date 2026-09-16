"""内置技能实现。

安全约定：
* 计算器使用 `ast` 白名单求值，绝不使用 `eval()`；
* 网页抓取禁止访问内网 / 本地地址（可在配置里显式放开），并限制响应大小；
* 所有技能都带超时与结果截断，避免拖垮对话。
"""

from __future__ import annotations

import ast
import asyncio
import ipaddress
import json
import math
import operator
import re
import socket
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx

from app.skills.base import BaseSkill, SkillArg, SkillError, SkillField, SkillSpec

DEFAULT_TIMEOUT = 20.0
DEFAULT_MAX_CHARS = 4000
USER_AGENT = "AI-Chat-Assistant/1.0 (+skills)"


# --------------------------------------------------------------------------- #
# 1. 计算器
# --------------------------------------------------------------------------- #
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "pow": pow,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "asin": math.asin,
    "acos": math.acos,
    "atan": math.atan,
    "floor": math.floor,
    "ceil": math.ceil,
    "factorial": math.factorial,
    "radians": math.radians,
    "degrees": math.degrees,
}
_CONSTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


def _eval_node(node: ast.AST) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, bool)):
            return node.value
        raise SkillError("表达式只支持数字常量")
    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise SkillError("不支持的运算符")
        return op(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise SkillError("不支持的一元运算符")
        return op(_eval_node(node.operand))
    if isinstance(node, ast.Name):
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        raise SkillError(f"未知的常量：{node.id}")
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise SkillError("只允许调用常见数学函数（sqrt/log/sin/round/abs...）")
        args = [_eval_node(a) for a in node.args]
        return _FUNCS[node.func.id](*args)
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval_node(e) for e in node.elts]
    raise SkillError("表达式包含不被允许的语法")


class CalculatorSkill(BaseSkill):
    """安全数学计算器（AST 白名单，无 eval）。"""

    spec = SkillSpec(
        type="calculator",
        name="计算器",
        description="执行数学计算。当用户给出算术表达式、需要精确计算（加减乘除、幂、开方、三角函数、百分比）时使用。",
        icon="CalculatorOutlined",
        category="general",
        fields=[
            SkillField(
                key="precision",
                label="结果小数位",
                type="integer",
                default=10,
                help="保留的小数位数，默认 10",
            )
        ],
        args=[
            SkillArg(
                name="expression",
                type="string",
                description="要计算的数学表达式，例如 (23*17+8)/3、sqrt(2)、sin(pi/6)",
                required=True,
            )
        ],
    )

    async def run(self, expression: str = "", **_: Any) -> str:
        text = str(expression or "").strip()
        if not text:
            raise SkillError("缺少数学表达式")
        # 容错：去掉用户口语与多余符号
        cleaned = text.replace("×", "*").replace("÷", "/").replace("^", "**").replace("，", ",")
        cleaned = re.sub(r"[^\dA-Za-z_+\-*/%().,\s\[\]]", "", cleaned).strip()
        if not cleaned:
            raise SkillError("表达式中没有可计算的字符")
        try:
            tree = ast.parse(cleaned, mode="eval")
        except SyntaxError as exc:
            raise SkillError(f"表达式语法错误：{cleaned}") from exc
        result = _eval_node(tree)
        precision = max(0, min(15, self.cfg_int("precision", 10)))
        if isinstance(result, float):
            if math.isnan(result) or math.isinf(result):
                raise SkillError("计算结果不是有效数字")
            shown = round(result, precision)
            shown = int(shown) if shown == int(shown) and abs(shown) < 1e15 else shown
        else:
            shown = result
        return f"表达式 {cleaned} = {shown}"


# --------------------------------------------------------------------------- #
# 2. 当前时间
# --------------------------------------------------------------------------- #
class CurrentTimeSkill(BaseSkill):
    """返回当前日期时间（可配置时区）。"""

    spec = SkillSpec(
        type="current_time",
        name="当前时间",
        description="获取当前日期、时间与星期。当用户询问今天几号、现在几点、星期几，或需要以当前时间为基准做推理时使用。",
        icon="ClockCircleOutlined",
        category="general",
        fields=[
            SkillField(
                key="timezone",
                label="时区",
                type="string",
                default="Asia/Shanghai",
                placeholder="Asia/Shanghai",
                help="IANA 时区名，默认 Asia/Shanghai",
            ),
            SkillField(
                key="format",
                label="时间格式",
                type="string",
                default="%Y-%m-%d %H:%M:%S",
                help="Python strftime 格式",
            ),
        ],
        args=[
            SkillArg(
                name="timezone",
                type="string",
                description="可选：临时指定时区（如 Asia/Tokyo、UTC），留空使用技能默认时区",
                required=False,
            )
        ],
    )

    async def run(self, timezone: str = "", **_: Any) -> str:
        tz_name = str(timezone or self.cfg("timezone", "Asia/Shanghai")).strip()
        tz = _resolve_timezone(tz_name)
        now = datetime.now(tz)
        fmt = str(self.cfg("format", "%Y-%m-%d %H:%M:%S"))
        weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
        return (
            f"当前时间（{tz_name}）：{now.strftime(fmt)}\n"
            f"星期：{weekdays[now.weekday()]}\n"
            f"UTC 时间：{now.astimezone(_resolve_timezone('UTC')).strftime('%Y-%m-%d %H:%M:%S')}"
        )


# --------------------------------------------------------------------------- #
# 3. 网页抓取
# --------------------------------------------------------------------------- #
_SCRIPT_STYLE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.I | re.S)
_TAG = re.compile(r"<[^>]+>")
_BLANK = re.compile(r"\n{3,}")
_SPACE = re.compile(r"[ \t\u3000]{2,}")

_PRIVATE_HINT = (
    "出于安全考虑，默认禁止抓取内网 / 本地地址（localhost、127.0.0.1、10.x、172.16-31.x、192.168.x、169.254.x）。"
    "如确需访问，请在该技能配置中把「允许访问内网」打开。"
)


_FALLBACK_OFFSETS: dict[str, int] = {
    "asia/shanghai": 8,
    "asia/chongqing": 8,
    "asia/harbin": 8,
    "asia/hong_kong": 8,
    "asia/taipei": 8,
    "asia/singapore": 8,
    "asia/tokyo": 9,
    "asia/seoul": 9,
    "utc": 0,
    "etc/utc": 0,
    "gmt": 0,
}


def _resolve_timezone(name: str):
    """解析时区；Windows 上缺少 IANA 时区库时退化为固定偏移。

    正常部署建议安装 `tzdata`（已写入 requirements.txt），这样支持全部时区与夏令时。
    """
    key = (name or "UTC").strip()
    try:
        return ZoneInfo(key)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        pass
    offset = _FALLBACK_OFFSETS.get(key.lower())
    if offset is None:
        # 再看是否形如 UTC+8 / +08:00
        match = re.fullmatch(r"(?:utc|gmt)?\s*([+-])(\d{1,2})(?::?(\d{2}))?", key, flags=re.I)
        if match:
            sign = 1 if match.group(1) == "+" else -1
            hours = int(match.group(2))
            minutes = int(match.group(3) or 0)
            offset = sign * hours + sign * minutes / 60
    if offset is None:
        raise SkillError(
            f"未知时区：{key}。请使用 IANA 时区名（如 Asia/Shanghai、UTC），"
            "或在服务器上安装 tzdata：pip install tzdata"
        )
    from datetime import timedelta, timezone as dt_timezone

    return dt_timezone(timedelta(hours=offset))


def _is_private_host(host: str) -> bool:
    if not host:
        return True
    if host.lower() in {"localhost", "localhost.localdomain", "ip6-localhost"}:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        address = info[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


def html_to_text(html: str) -> str:
    """极简 HTML → 文本（去脚本样式、去标签、还原实体）。"""
    text = _SCRIPT_STYLE.sub(" ", html)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</(p|div|li|h[1-6]|tr)>", "\n", text, flags=re.I)
    text = _TAG.sub(" ", text)
    text = unescape(text)
    text = _SPACE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    return _BLANK.sub("\n\n", "\n".join(line for line in lines if line)).strip()


class WebFetchSkill(BaseSkill):
    """抓取指定 URL 的正文内容。"""

    spec = SkillSpec(
        type="web_fetch",
        name="网页抓取",
        description="抓取一个网页或接口地址的文本内容。当用户给出具体 URL，或需要阅读某个已知链接的正文时使用。",
        icon="GlobalOutlined",
        category="web",
        fields=[
            SkillField(
                key="max_chars",
                label="返回最大字符数",
                type="integer",
                default=DEFAULT_MAX_CHARS,
                help="超出部分会被截断，避免超长内容占满上下文",
            ),
            SkillField(key="timeout", label="超时（秒）", type="number", default=DEFAULT_TIMEOUT),
            SkillField(
                key="allow_private",
                label="允许访问内网",
                type="boolean",
                default=False,
                help="开启后可抓取 localhost / 内网地址（有 SSRF 风险，请谨慎）",
            ),
        ],
        args=[
            SkillArg(name="url", type="string", description="要抓取的完整 URL（http/https）", required=True),
            SkillArg(
                name="max_chars",
                type="integer",
                description="可选：本次返回的最大字符数",
                required=False,
            ),
        ],
    )

    async def run(self, url: str = "", max_chars: int | None = None, **_: Any) -> str:
        target = str(url or "").strip()
        if not target:
            raise SkillError("缺少 url 参数")
        parsed = urlparse(target if "://" in target else f"https://{target}")
        if parsed.scheme not in {"http", "https"}:
            raise SkillError("只支持 http / https 地址")
        if not self.cfg_bool("allow_private", False) and _is_private_host(parsed.hostname or ""):
            raise SkillError(_PRIVATE_HINT)

        limit = int(max_chars or self.cfg_int("max_chars", DEFAULT_MAX_CHARS))
        timeout = self.cfg_float("timeout", DEFAULT_TIMEOUT)
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
            ) as client:
                response = await client.get(urlunparse(parsed))
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                body = response.text
        except httpx.HTTPStatusError as exc:
            raise SkillError(f"请求返回 {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise SkillError(f"请求失败：{type(exc).__name__}") from exc

        if "json" in content_type:
            text = body
        else:
            text = html_to_text(body)
        text = text.strip()
        if not text:
            raise SkillError("页面没有可提取的文本内容")
        truncated = len(text) > limit
        return (
            f"来源：{parsed.geturl()}\n"
            f"（内容{'已截断，' if truncated else ''}共 {len(text)} 字符）\n\n"
            f"{text[:limit]}"
        )


# --------------------------------------------------------------------------- #
# 4. 联网搜索（Tavily 兼容）
# --------------------------------------------------------------------------- #
class WebSearchSkill(BaseSkill):
    """联网搜索：调用 Tavily 兼容的搜索接口。"""

    spec = SkillSpec(
        type="web_search",
        name="联网搜索",
        description="在互联网上搜索最新信息。当问题涉及实时新闻、最新版本、近期事件，或需要超出模型知识范围的外部资料时使用。",
        icon="SearchOutlined",
        category="web",
        fields=[
            SkillField(
                key="api_key",
                label="API Key",
                type="password",
                required=True,
                secret=True,
                placeholder="tvly-xxxxxxxx",
                help="Tavily（https://tavily.com）或任何兼容 /search 接口的服务",
            ),
            SkillField(
                key="base_url",
                label="搜索接口地址",
                type="string",
                default="https://api.tavily.com",
                help="默认 Tavily；也可填自建 / 代理网关地址",
            ),
            SkillField(key="max_results", label="返回条数", type="integer", default=5),
            SkillField(
                key="search_depth",
                label="检索深度",
                type="select",
                default="basic",
                options=[
                    {"value": "basic", "label": "basic（快）"},
                    {"value": "advanced", "label": "advanced（更全，更慢）"},
                ],
            ),
            SkillField(key="timeout", label="超时（秒）", type="number", default=DEFAULT_TIMEOUT),
        ],
        args=[
            SkillArg(name="query", type="string", description="搜索关键词或问题", required=True),
            SkillArg(name="max_results", type="integer", description="可选：本次返回条数", required=False),
        ],
    )

    async def run(self, query: str = "", max_results: int | None = None, **_: Any) -> str:
        keyword = str(query or "").strip()
        if not keyword:
            raise SkillError("缺少搜索关键词")
        api_key = self.require("api_key", "API Key")
        base_url = str(self.cfg("base_url", "https://api.tavily.com")).rstrip("/")
        payload = {
            "api_key": api_key,
            "query": keyword,
            "max_results": int(max_results or self.cfg_int("max_results", 5)),
            "search_depth": self.cfg("search_depth", "basic"),
            "include_answer": False,
            "include_raw_content": False,
        }
        timeout = self.cfg_float("timeout", DEFAULT_TIMEOUT)
        try:
            async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT}) as client:
                response = await client.post(f"{base_url}/search", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:200]
            raise SkillError(f"搜索接口返回 {exc.response.status_code}：{detail}") from exc
        except httpx.HTTPError as exc:
            raise SkillError(f"搜索请求失败：{type(exc).__name__}") from exc
        except ValueError as exc:
            raise SkillError("搜索接口返回的不是合法 JSON") from exc

        results = data.get("results") or data.get("data") or []
        if not results:
            return f"未搜索到与「{keyword}」相关的结果。"
        lines = [f"关键词「{keyword}」的搜索结果："]
        for index, item in enumerate(results[:10], start=1):
            title = item.get("title") or item.get("name") or "未命名"
            url = item.get("url") or item.get("link") or ""
            content = (item.get("content") or item.get("snippet") or "").strip().replace("\n", " ")
            lines.append(f"\n[{index}] {title}\n链接：{url}\n摘要：{content[:400]}")
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 5. 自定义 HTTP 接口
# --------------------------------------------------------------------------- #
class HttpRequestSkill(BaseSkill):
    """把任意 HTTP 接口包装成模型可调用的技能。"""

    spec = SkillSpec(
        type="http_request",
        name="自定义 HTTP 接口",
        description="调用自定义 HTTP 接口（企业内部 API、Webhook、第三方服务）。",
        icon="ApiOutlined",
        category="custom",
        fields=[
            SkillField(
                key="url",
                label="接口地址",
                type="string",
                required=True,
                placeholder="https://api.example.com/v1/search",
            ),
            SkillField(
                key="method",
                label="请求方法",
                type="select",
                default="GET",
                options=[{"value": m, "label": m} for m in ("GET", "POST", "PUT", "PATCH", "DELETE")],
            ),
            SkillField(
                key="args_schema",
                label="入参定义（JSON）",
                type="json",
                default='{\n  "keyword": {"type": "string", "description": "查询关键词"}\n}',
                help='示例：{"keyword": {"type": "string", "description": "查询关键词"}}；'
                "支持 string / number / integer / boolean 四种类型",
            ),
            SkillField(
                key="params_in",
                label="参数传递方式",
                type="select",
                default="auto",
                options=[
                    {"value": "auto", "label": "自动（GET/DELETE 用 query，其它用 body）"},
                    {"value": "query", "label": "Query 参数"},
                    {"value": "body", "label": "JSON Body"},
                ],
            ),
            SkillField(
                key="headers",
                label="请求头（JSON）",
                type="json",
                default="{}",
                help='例如 {"Authorization": "Bearer xxx"}',
            ),
            SkillField(
                key="tool_description",
                label="用途说明",
                type="text",
                default="",
                help="告诉模型什么时候该调用这个接口；留空则使用技能描述",
            ),
            SkillField(
                key="result_path",
                label="结果字段路径",
                type="string",
                default="",
                placeholder="data.items",
                help="可选：只取响应 JSON 中的某个字段（用 . 逐层下钻）",
            ),
            SkillField(key="max_chars", label="返回最大字符数", type="integer", default=DEFAULT_MAX_CHARS),
            SkillField(key="timeout", label="超时（秒）", type="number", default=DEFAULT_TIMEOUT),
        ],
        uses_dynamic_args=True,
    )

    def test_arguments(self) -> dict[str, Any]:
        from app.skills.registry import parse_args_schema

        args = parse_args_schema(self.cfg("args_schema"))
        return {item["name"]: "" for item in args} or {"keyword": ""}

    async def run(self, **kwargs: Any) -> str:
        url = self.require("url", "接口地址")
        method = str(self.cfg("method", "GET")).upper()
        timeout = self.cfg_float("timeout", DEFAULT_TIMEOUT)
        headers = _load_json_object(self.cfg("headers"), "请求头")
        params_in = str(self.cfg("params_in", "auto")).lower()
        args = {k: v for k, v in kwargs.items() if v not in (None, "")}

        if params_in == "auto":
            params_in = "query" if method in {"GET", "DELETE", "HEAD"} else "body"

        try:
            async with httpx.AsyncClient(timeout=timeout, headers={"User-Agent": USER_AGENT, **headers}) as client:
                request_kwargs: dict[str, Any] = {}
                if params_in == "query":
                    request_kwargs["params"] = args
                else:
                    request_kwargs["json"] = args
                response = await client.request(method, url, **request_kwargs)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "json" in content_type:
                    try:
                        payload: Any = response.json()
                    except ValueError:
                        payload = response.text
                else:
                    payload = response.text
        except httpx.HTTPStatusError as exc:
            raise SkillError(f"接口返回 {exc.response.status_code}：{exc.response.text[:200]}") from exc
        except httpx.HTTPError as exc:
            raise SkillError(f"请求失败：{type(exc).__name__}") from exc

        result_path = str(self.cfg("result_path", "")).strip()
        if result_path and isinstance(payload, (dict, list)):
            payload = _dig(payload, result_path)

        limit = self.cfg_int("max_chars", DEFAULT_MAX_CHARS)
        if isinstance(payload, (dict, list)):
            text = json.dumps(payload, ensure_ascii=False, indent=2)
        else:
            text = str(payload)
        return f"接口 {method} {url} 返回：\n{text[:limit]}"


def _load_json_object(raw: Any, label: str) -> dict[str, Any]:
    if raw in (None, "", {}):
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise SkillError(f"{label}不是合法 JSON") from exc
    if not isinstance(parsed, dict):
        raise SkillError(f"{label}必须是 JSON 对象")
    return {str(k): str(v) for k, v in parsed.items()}


def _dig(payload: Any, path: str) -> Any:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if 0 <= index < len(current) else None
        else:
            return payload
    return payload if current is None else current


BUILTIN_SKILLS: list[type[BaseSkill]] = [
    CalculatorSkill,
    CurrentTimeSkill,
    WebSearchSkill,
    WebFetchSkill,
    HttpRequestSkill,
]


__all__ = [
    "BUILTIN_SKILLS",
    "CalculatorSkill",
    "CurrentTimeSkill",
    "HttpRequestSkill",
    "WebFetchSkill",
    "WebSearchSkill",
    "html_to_text",
]
