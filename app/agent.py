from typing import AsyncGenerator
import os
import traceback
import httpx
from browser_use.browser.context import BrowserContext
from .models import oai_compatible_models
from .utils import (
    get_system_prompt, 
    refine_chat_history, 
    to_chunk_data, 
    refine_assistant_message,
    wrap_chunk,
    random_uuid,
    wrap_toolcall_response,
    refine_mcp_response
)
import logging
import openai
import json
from .toolcalls import execute_toolcall, get_context_aware_available_toolcalls

logger = logging.getLogger()


async def prompt(messages: list[dict[str, str]], browser_context: BrowserContext, **_) -> AsyncGenerator[str, None]:
    llm = openai.AsyncClient(
        base_url=os.getenv("LLM_BASE_URL", "http://localmodel:65534/v1"),
        api_key=os.getenv("LLM_API_KEY", "no-need")
    )

    messages = await refine_chat_history(messages, get_system_prompt())
    
    response_uuid = random_uuid()
    error_details = ''
    error_message = ''
    calls = 0
    
    functions = await get_context_aware_available_toolcalls(browser_context)

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
                        response = await execute_toolcall(
                            ctx=browser_context, 
                            tool_name=_name,
                            args=_args
                        )

                        if response.success:
                            yield to_chunk_data(
                                wrap_toolcall_response(
                                    uuid=response_uuid,
                                    fn_name=_name,
                                    args=_args,
                                    result=response.result
                                )
                            )

                            result = json.dumps(refine_mcp_response(response.result))

                        else:
                            result = f"Tool call failed: {response.error}"

                    except Exception as e:
                        logger.error(f"{e}", exc_info=True)
                        result = f"Something went wrong: {str(e)}" 
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
