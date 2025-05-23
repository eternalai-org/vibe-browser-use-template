from typing import AsyncGenerator
from langchain_openai import ChatOpenAI
import os
from .callbacks import (
    on_task_completed, 
    on_task_start
)
import traceback
import httpx

from browser_use import Agent
from browser_use.browser.context import BrowserContext
from .controllers import get_controler
from .models import browser_use_custom_models, oai_compatible_models
from .utils import get_system_prompt, repair_json_no_except, refine_chat_history, to_chunk_data, refine_assistant_message, wrap_chunk, random_uuid
import logging
import openai
import json

logger = logging.getLogger()

async def browse(task_query: str, ctx: BrowserContext, **_) -> AsyncGenerator[str, None]:

    controller = get_controler()
    system_prompt = get_system_prompt()

    model = ChatOpenAI(
        model=os.getenv("LLM_MODEL_ID", 'local-llm'),
        openai_api_base=os.getenv("LLM_BASE_URL", 'http://localhost:65534/v1'),
        openai_api_key=os.getenv("LLM_API_KEY", 'no-need'),
    )

    current_agent = Agent(
        task=task_query,
        llm=model,
        page_extraction_llm=model,
        planner_llm=model,
        browser_context=ctx,
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

            yield parsed.message
        except Exception as err:
            logger.info(f"Exception raised while parsing final answer: {err}")
            yield f"task {task_query!r} completed!"

    yield f"task {task_query!r} completed"
    

async def execute_openai_compatible_toolcall(
    ctx: BrowserContext,
    name: str,
    args: dict[str, str]
) -> AsyncGenerator[str, None]:
    logger.info(f"Executing tool call: {name} with args: {args}")
    
    if name == "xbrowse":
        task = args.get("task", "")

        if not task:
            yield "No task provided for xbrowse tool call."
            return

        async for msg in browse(task, ctx):
            yield msg
            
        return

    yield f"Unknown tool call: {name}; only xbrowse is available."


async def prompt(messages: list[dict[str, str]], browser_context: BrowserContext, **_) -> AsyncGenerator[str, None]:
    functions = [
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
        }
    ]

    llm = openai.AsyncClient(
        base_url=os.getenv("LLM_BASE_URL", "http://localmodel:65534/v1"),
        api_key=os.getenv("LLM_API_KEY", "no-need")
    )

    messages = await refine_chat_history(messages, get_system_prompt())
    
    response_uuid = random_uuid()
    error_details = ''
    error_message = ''
    calls = 0

    try:
        completion = await llm.chat.completions.create(
            model=os.getenv("LLM_MODEL_ID", 'local-llm'),
            messages=messages,
            tools=functions,
            tool_choice="auto",
            max_tokens=256
        )
        
        if completion.choices[0].message.content:
            yield completion.choices[0].message.content

        messages.append(await refine_assistant_message(completion.choices[0].message.model_dump()))
        
        while completion.choices[0].message.tool_calls is not None and len(completion.choices[0].message.tool_calls) > 0:
            calls += len(completion.choices[0].message.tool_calls)
            executed = set([])
            
            for call in completion.choices[0].message.tool_calls:
                _id, _name = call.id, call.function.name    
                _args = json.loads(call.function.arguments)
                result, has_exception = '', False
                identity = _name + call.function.arguments

                if identity in executed:
                    result = f"Tool call `{_name}` has been executed before with the same arguments: {_args}. Skipping"
                    
                else:
                    executed.add(identity)

                    yield await to_chunk_data(
                        await wrap_chunk(
                            response_uuid,
                            f"**Calling**: {_name}...\n",
                            role="tool",
                        )
                    )

                    try:
                        async for msg in execute_openai_compatible_toolcall(
                            ctx=browser_context, 
                            name=_name,
                            args=_args
                        ):
                            yield msg

                            if isinstance(msg, str):
                                result += msg + '\n'

                    except Exception as e:
                        logger.warning(f"{e}")

                        yield await to_chunk_data(
                            await wrap_chunk(
                                response_uuid,
                                f"Exception raised. Pausing...\n",
                                role="tool"
                            )
                        )

                        result = f"Something went wrong, ask the user to solve it manually and notify you again once when it is resolved. After then, Re-execute {_name} with these arguments: {_args}" 
                        has_exception = True

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": _id,
                        "content": result
                    }
                )

                if has_exception:
                    break 

                need_toolcalls = calls < 10 and not has_exception

                completion = await llm.chat.completions.create(
                    messages=messages,
                    model=os.getenv("LLM_MODEL_ID", 'local-llm'),
                    tools=functions if need_toolcalls else openai._types.NOT_GIVEN,  # type: ignore
                    tool_choice="auto" if need_toolcalls else openai._types.NOT_GIVEN,  # type: ignore
                    max_tokens=512
                )

                logger.info(f"Assistant: {completion.choices[0].message.content!r}")

                if completion.choices[0].message.content:
                    yield completion.choices[0].message.content

                messages.append(await refine_assistant_message(completion.choices[0].message.model_dump()))
      
    except openai.APIConnectionError as e:
        error_message=f"Failed to connect to language model: {e}"
        error_details = traceback.format_exc(limit=-6)

    except openai.RateLimitError as e:
        error_message=f"Rate limit error: {e}"

    except openai.APIError as e:
        error_message=f"Language model returned an API Error: {e}"

    except httpx.HTTPStatusError as e:
        error_message=f"HTTP status error: {e}"
        
    except Exception as e:
        error_message=f"Unhandled error: {e}"
        error_details = traceback.format_exc(limit=-6)
        
    finally:
        if error_message:

            logger.error(f"Error occurred: {error_message}")
            logger.error(f"Error details: {error_details}")

            yield await to_chunk_data(
                oai_compatible_models.PromptErrorResponse(
                    message=error_message, 
                    details=error_details
                )
            )
