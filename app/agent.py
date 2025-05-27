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

from .signals import UnauthorizedAccess
from .controllers import check_authorization, ensure_url

logger = logging.getLogger()

async def browse(task_query: str, ctx: BrowserContext, **_) -> AsyncGenerator[str, None]:
    controller = get_controler()
    extend_system_message = """
REMEMBER the most important RULE:

You are an expert assistant specialized in using the website https://polymarket.com/.
You must ONLY perform tasks, answer questions, or retrieve information that is directly related to Polymarket.
Do NOT browse, reference, or use any other website or source.
If a user asks for something unrelated to Polymarket, politely respond that you can only assist with tasks on https://polymarket.com/.
Always use the Polymarket website as your sole source of information and actions.

IMPORTANT: If you encounter an authentication page (such as login with Google) or a page requiring the user to add funds to continue, you MUST STOP and inform the user that they need to complete authentication or add funds themselves before you can proceed. Do not attempt to bypass or automate these steps. Wait for user confirmation before continuing.

When you detect an authentication page, you should:
1. Stop immediately
2. Inform the user that authentication is required
3. Wait for the user to complete authentication
4. Only continue after the user confirms authentication is complete
"""
    system_prompt = get_system_prompt() + extend_system_message

    logger.info(f"[System Prompt] {system_prompt}")

    model = ChatOpenAI(
        model=os.getenv("LLM_MODEL_ID", 'local-llm'),
        openai_api_base=os.getenv("LLM_BASE_URL", 'http://localhost:65534/v1'),
        openai_api_key=os.getenv("LLM_API_KEY", 'no-need'),
    )

    current_agent = Agent(
        task=task_query,
        llm=model,
        # page_extraction_llm=model,
        # planner_llm=model,
        browser_context=ctx,
        controller=controller,
        extend_system_message=system_prompt,
        is_planner_reasoning=False,
        use_vision=True,
        use_vision_for_planner=True,
        enable_memory=False
    )

    while True:
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
        break

async def get_markets(
    ctx: BrowserContext,
    category: str = "all",
    sorting: str = "volume",
    frequency: str = "all"
) -> AsyncGenerator[str, None]:
    # Implement get_markets logic here
    await ensure_url(ctx, 'https://polymarket.com')

    yield f"get_markets tool is not yet implemented."
    return

async def place_order(
    ctx: BrowserContext,
    market_id: str,
    order_type: str,
    side: str,
    amount: float,
    price: float = None
) -> AsyncGenerator[str, None]:
    
    # check authentication
    if not await check_authorization(ctx):
        await ensure_url(ctx, 'https://polymarket.com')
        raise UnauthorizedAccess("Please sign in to your Polymarket account first.")

    # Implement place_order logic here
    yield f"place_order tool is not yet implemented."
    return

async def execute_openai_compatible_toolcall(
    ctx: BrowserContext,
    name: str,
    args: dict[str, str]
) -> AsyncGenerator[str, None]:
    logger.info(f"Executing tool call: {name} with args: {args}")

    if not name or not args:
        # allow LLM to answer without tool calls
        yield "No tool call name or arguments provided."


    if name == "get_markets":
    #     # Implement get_markets tool call here

        # check if the user is on the right page
        # if not, then go to the right page

        task = f"Find the market from user request: {args}"
        async for msg in browse(task, ctx):
            yield msg

    #     # yield "get_markets tool is not yet implemented."
    #     return

    if name == "place_order":
        # Implement place_order tool call here

        # check if the user is on the right page
        # if not, then go to the right page

        task = "Place order from user request"
        async for msg in browse(task, ctx):
            yield msg


    #     yield "place_order tool is not yet implemented."
    #     return

    if name == "xbrowse":
        task = args.get("task", "")

        if not task:
            yield "No task provided for xbrowse tool call."
            return

        async for msg in browse(task, ctx):
            yield msg
            
        return 

    yield f"Unknown tool call: {name}; Available tools are: get_markets, place_order"


async def prompt(messages: list[dict[str, str]], browser_context: BrowserContext, **_) -> AsyncGenerator[str, None]:
    functions = [
        {
            "type": "function",
            "function": {
                "name": "get_markets",
                "description": "Get list of markets from Polymarket with optional filtering or search parameters",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "string",
                            "description": "Keywords to search markets"
                        },

                        "category": {
                            "type": "string",
                            "enum": ["all", "crypto", "politics", "sports", "entertainment", "other"],
                            "description": "Category of markets to filter by",
                        },
                        "sorting": {
                            "type": "string",
                            "enum": ["24hr_volume", "total_volume", "liquidity", "newest", "ending_soon", "competitive"],
                            "description": "How to sort the markets"
                        },
                        "frequency": {
                            "type": "string",
                            "enum": ["all", "daily", "weekly", "monthly"],
                            "description": "Frequency of market updates"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "place_order",
                "description": "Place a market or limit order on Polymarket",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "market_id": {
                            "type": "string",
                            "description": "ID of the market to place order in"
                        },
                        "order_type": {
                            "type": "string",
                            "enum": ["market", "limit"],
                            "description": "Type of order to place"
                        },
                        "side": {
                            "type": "string",
                            "enum": ["buy", "sell"],
                            "description": "Whether to buy or sell"
                        },
                        "amount": {
                            "type": "number",
                            "description": "Amount to buy/sell"
                        },
                        "price": {
                            "type": "number",
                            "description": "Price for limit orders. Required if order_type is limit"
                        }
                    },
                    "required": ["market_id", "order_type", "side", "amount"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "xbrowse",
                "description": "Ask xbrowser to do a task in the browser like replying an email or anything that there is no tools to execute, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "Task description to execute in browser. It should be as much detail as possible, step-by-step to achieve the task."
                        }    
                    },
                    "required": ["task"],
                    "additionalProperties": False
                },
                "strict": True
            }
        },
    ]

    llm = openai.AsyncClient(
        base_url=os.getenv("LLM_BASE_URL", "http://localmodel:65534/v1"),
        api_key=os.getenv("LLM_API_KEY", "no-need")
    )

    messages = await refine_chat_history(messages, get_system_prompt())

    logger.info(f"Messages: {messages!r}")
    
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

        logger.info(f"Tool calls: {completion.choices[0].message.tool_calls!r}")
        
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

                elif has_exception:
                    result = f"Exception raised. Skipping task...\n"

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
                        logger.error(f"{e}", exc_info=True)

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
