"""
PyRITAdapter：将 MetaAgent 动态生成的 DynamicTarget.run 适配为 PyRIT 的 PromptTarget。

在 send_prompt_async 中，把 PyRIT 发来的 prompt 转交给 target.run(**{run_param_name: prompt})，
并将返回内容封装成 PyRIT 的 Message 返回。
"""

from __future__ import annotations

import asyncio
from typing import Any

from pyrit.models import Message, construct_response_from_request
from pyrit.prompt_target.common.prompt_target import PromptTarget


class PyRITAdapter(PromptTarget):
    """
    适配器：把任意实现了 run(**kwargs) 的对象（如 MetaAgent 生成的 DynamicTarget 实例）
    包装成 PyRIT 的 PromptTarget，供 RedTeamingOrchestrator / PromptSendingAttack 等调用。
    """

    def __init__(
        self,
        *,
        dynamic_target: Any,
        run_param_name: str = "message",
        extra_run_kwargs: dict[str, Any] | None = None,
        model_name: str = "meta_agent_dynamic",
        **kwargs: Any,
    ):
        """
        Args:
            dynamic_target: 动态入口封装对象，需提供 run(**kwargs) 方法（如 DynamicTarget 实例）。
            run_param_name: 调用 run 时「主输入」的键名，默认 "message"。普适化时可由 LLM 检测的 entry.params[0].name 传入。
            extra_run_kwargs: 调用 run 时额外固定参数，如 {"stream": False}，与主输入一起传入。
            model_name: 用于 PyRIT 标识的模型名。
            **kwargs: 传给 PromptTarget 的其它参数（如 endpoint, verbose）。
        """
        super().__init__(model_name=model_name, **kwargs)
        self._target = dynamic_target
        self._run_param_name = run_param_name
        self._extra_run_kwargs = dict(extra_run_kwargs or {})
        self.last_request_value: str = ""  # 最近一次发给 target 的 prompt，供攻击脚本记录

    def _validate_request(self, *, message: Message) -> None:
        if not message.message_pieces:
            raise ValueError("Message must have at least one piece.")
        piece = message.get_piece(0)
        if piece.converted_value is None and piece.original_value is None:
            raise ValueError("Message piece must have convertible or original value.")

    async def send_prompt_async(self, *, message: Message) -> list[Message]:
        self._validate_request(message=message)
        prompt_text = message.get_value(0)
        self.last_request_value = prompt_text
        request_piece = message.get_piece(0)

        def _run_sync() -> str:
            kwargs = {self._run_param_name: prompt_text, **self._extra_run_kwargs}
            out = self._target.run(**kwargs)
            return str(out) if out is not None else ""

        loop = asyncio.get_event_loop()
        response_text = await loop.run_in_executor(None, _run_sync)
        response_message = construct_response_from_request(request_piece, [response_text])
        return [response_message]
