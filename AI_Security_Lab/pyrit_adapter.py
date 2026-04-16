"""
PyRITAdapter：将任意实现 run(**kwargs) 的 target（如 HttpTarget）接入 PyRIT PromptTarget。

send_prompt_async 把 PyRIT 的 prompt 转为 target.run(**{run_param_name: prompt, **extra})，
并封装为 PyRIT Message；与 MetaAgent / inproc 无耦合。
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

from pyrit.models import Message, construct_response_from_request
from pyrit.prompt_target.common.prompt_target import PromptTarget


class PyRITAdapter(PromptTarget):
    """把实现了 run(**kwargs) 的目标（HTTP 或其它）包装为 PyRIT PromptTarget。"""

    def __init__(
        self,
        *,
        dynamic_target: Any,
        run_param_name: str = "message",
        extra_run_kwargs: dict[str, Any] | None = None,
        model_name: str = "http_agent_target",
        **kwargs: Any,
    ):
        """
        Args:
            dynamic_target: 需提供 run(**kwargs)，例如 HttpTarget（由 registry 的 input_key 决定 kwargs 键名）。
            run_param_name: 主输入在 run() 中的参数名，与 agents.yaml 的 input_key 一致。
            extra_run_kwargs: 调用 run 时额外固定参数，如 {"stream": False}，与主输入一起传入。
            model_name: 用于 PyRIT 标识的模型名。
            **kwargs: 传给 PromptTarget 的其它参数（如 endpoint, verbose）。
        """
        super().__init__(model_name=model_name, **kwargs)
        self._target = dynamic_target
        self._run_param_name = run_param_name
        self._extra_run_kwargs = dict(extra_run_kwargs or {})
        self.last_request_value: str = ""
        self.last_response_value: str = ""
        self.last_run_kwargs: dict[str, Any] = {}
        self.last_error: str = ""

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
        self.last_error = ""
        self.last_run_kwargs = {self._run_param_name: prompt_text, **self._extra_run_kwargs}
        request_piece = message.get_piece(0)

        def _run_sync() -> str:
            kwargs = dict(self.last_run_kwargs)
            out = self._target.run(**kwargs)
            if isinstance(out, dict):
                return str(out)
            return str(out) if out is not None else ""

        try:
            loop = asyncio.get_event_loop()
            response_text = await loop.run_in_executor(None, _run_sync)
            self.last_response_value = response_text
        except Exception:
            self.last_error = traceback.format_exc()
            raise

        response_message = construct_response_from_request(request_piece, [response_text])
        return [response_message]

