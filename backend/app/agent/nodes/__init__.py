"""图节点：每个节点都是 `async def node(state, ctx) -> dict` 的独立函数。

不把业务逻辑塞进 graph.py 的闭包里，单测可以直接 await 某个节点。
"""

from . import (
    audit,
    execute,
    fail,
    finalize,
    inspect,
    intake,
    plan,
    repair_step,
    replan,
    report,
    verify,
)

NODE_MODULES = (
    intake,
    inspect,
    plan,
    execute,
    repair_step,
    verify,
    replan,
    report,
    audit,
    finalize,
    fail,
)

__all__ = [module.__name__.rsplit(".", 1)[-1] for module in NODE_MODULES]
