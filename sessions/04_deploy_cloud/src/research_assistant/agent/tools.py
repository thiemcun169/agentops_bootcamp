"""The agent's two tools: web search (Tavily) and a calculator."""
import ast
import logging
import operator

from langchain.tools import tool
from tavily import TavilyClient

from research_assistant.core.config import get_settings

logger = logging.getLogger(__name__)

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg}


def _eval(node: ast.AST) -> float:
    """Arithmetic only: numbers and + - * / ** (the prototype used eval(), which runs any Python)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("only numbers and + - * / ** are allowed")


@tool
def calculate(expression: str) -> str:
    """Evaluate an arithmetic expression such as "12000 / 2.8"."""
    try:
        result = _eval(ast.parse(expression, mode="eval").body)
    except (ValueError, SyntaxError, ZeroDivisionError) as exc:
        result = f"error: {exc}"  # returned to the model so it can fix the expression
    logger.info("calculate(%s) -> %s", expression, result)
    return str(result)


@tool
def web_search(query: str) -> list[dict]:
    """Search the web; return title, url and a short snippet of the best results."""
    settings = get_settings()
    try:
        client = TavilyClient(api_key=settings.tavily_api_key.get_secret_value())
        results = client.search(query, max_results=settings.max_search_results)["results"]
    except Exception as exc:  # quota, network, bad key: tell the model instead of crashing the run
        logger.warning("web_search -> error %s", type(exc).__name__)
        return [{"error": f"search failed: {exc}"}]
    logger.info("web_search -> %d results", len(results))  # the query may quote the user: not logged
    return [{"title": r["title"], "url": r["url"], "content": r["content"][:500]} for r in results]
