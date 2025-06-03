from browser_use.browser.context import BrowserContext
from pydantic import BaseModel, model_validator
from .models import browser_use_custom_models 
from typing import Any, Generic, Optional, TypeVar, Callable, Awaitable
from browser_use import Controller
from .utils import get_system_prompt, repair_json_no_except
from langchain_openai import ChatOpenAI
import os
import logging
from .callbacks import on_task_completed, on_task_start
from browser_use import Agent

logger = logging.getLogger(__name__)


_generic_type = TypeVar('_generic_type')
class ResponseMessage(BaseModel, Generic[_generic_type]):
    result: Optional[_generic_type] = None
    error: Optional[str] = None
    success: bool = True

    @model_validator(mode="after")
    def refine_status(self):
        if self.error is not None:
            self.success = False

        return self

async def browse(ctx: BrowserContext, task: str, **_) -> ResponseMessage[str]:

    controller = Controller(
        output_model=browser_use_custom_models.FinalAgentResult
    )
    system_prompt = get_system_prompt()

    model = ChatOpenAI(
        model=os.getenv("LLM_MODEL_ID", 'local-llm'),
        openai_api_base=os.getenv("LLM_BASE_URL", 'http://localhost:65534/v1'),
        openai_api_key=os.getenv("LLM_API_KEY", 'no-need'),
    )

    current_agent = Agent(
        task=task,
        llm=model,
        page_extraction_llm=model,
        planner_llm=model,
        browser_session=ctx,
        controller=controller,
        extend_system_message=system_prompt,

        is_planner_reasoning=False,
        use_vision=True,
        use_vision_for_planner=True,
        enable_memory=False
    )

    res = await current_agent.run(
        max_steps=40,
        on_step_start=on_task_start, 
        on_step_end=on_task_completed
    )

    final_result = res.final_result()

    if final_result is not None:
        try:
            parsed: browser_use_custom_models.FinalAgentResult \
                = browser_use_custom_models.FinalAgentResult.model_validate_json(
                    repair_json_no_except(final_result)
                )

            if parsed.status == "pending":
                logger.info(f"Completed task in status {parsed.status}")

            return ResponseMessage(result=parsed.message)
        except Exception as err:
            logger.info(f"Exception raised while parsing final answer: {err}")
            return ResponseMessage(result=f"task {task!r} completed!")

    return ResponseMessage(result=f"task {task!r} completed")


async def get_context_aware_available_toolcalls(
    ctx: BrowserContext, 
    include_executable: bool = False
) -> list[tuple[dict[str, Any], Callable[[str, BrowserContext], Awaitable[ResponseMessage[Any]]]]]:
    toolcalls = [
        (
            {
                "type": "function",
                "function": {
                    "name": "xbrowse",
                    "description": "Ask the XBrowser to complete the browsing task, as you can not!",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task": {
                                "type": "string",
                                "description": "Task description to do in browser. It should be rich information. For instance, the user want to go shopping online, the task definition should be: what to buy, where and, or how to retrieve the needed information, etc."
                            }    
                        },
                        "required": ["task"],
                        "additionalProperties": False
                    },
                    "strict": True
                }
            }, 
            browse
        ),
        # other toolcalls here
    ]
    
    if include_executable:
        return toolcalls
    
    return [e[0] for e in toolcalls]

async def execute_toolcall(
    ctx: BrowserContext, 
    tool_name: str, 
    args: dict[str, Any]
) -> ResponseMessage[Any]:
    response_model = ResponseMessage[Any]

    for toolcall, executor in await get_context_aware_available_toolcalls(ctx, include_executable=True):
        if toolcall["function"]["name"] == tool_name:
            return await executor(ctx, **args)

    return response_model(error=f"Unavailable tool call: {tool_name}", success=False)
    