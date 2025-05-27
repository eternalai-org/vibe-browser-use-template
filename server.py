import logging
logging.basicConfig(level=logging.INFO)

import fastapi
import uvicorn
import asyncio
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
import os
from contextlib import asynccontextmanager
import sys
from typing import Union
from patchright.async_api import async_playwright 

from app.models.oai_compatible_models import (
    ChatCompletionStreamResponse, 
    PromptErrorResponse
)
from app import prompt
from typing import AsyncGenerator
import time
import uuid
import openai
# from browser_use import Browser, BrowserConfig
from browser_use.browser.context import BrowserContextConfig

from browser_use import BrowserSession, BrowserProfile, Agent

BROWSER_PROFILE_DIR = "/browser-data/profiles/persistent"

logger = logging.getLogger(__name__)

if not load_dotenv():
    logger.warning("hehe, .env not found")

_GLOBALS = {}

@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    processes: list[asyncio.subprocess.Process] = []

    BROWSER_WINDOW_SIZE_WIDTH = int(os.getenv("BROWSER_WINDOW_SIZE_WIDTH", 1920)) 
    BROWSER_WINDOW_SIZE_HEIGHT = int(os.getenv("BROWSER_WINDOW_SIZE_HEIGHT", 800)) 
    SCREEN_COLOR_DEPTH_BITS = int(os.getenv("SCREEN_COLOR_DEPTH_BITS", 24))
    DISPLAY = os.getenv("DISPLAY", ":99")
    NO_VNC_PORT = os.getenv("NO_VNC_PORT", 6080)
    CHROME_DEBUG_PORT = os.getenv("CHROME_DEBUG_PORT", 9222)
    os.environ['CDP_URL'] = f"http://localhost:{CHROME_DEBUG_PORT}"

    process = await asyncio.create_subprocess_shell(
        create_passwd_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()

    os.makedirs('/tmp/.X11-unix', exist_ok=True)
    os.makedirs('/tmp/.ICE-unix', exist_ok=True)
    os.makedirs(BROWSER_PROFILE_DIR, exist_ok=True)
    logger.info(f"Created {BROWSER_PROFILE_DIR}: {os.path.exists(BROWSER_PROFILE_DIR)}")
    os.makedirs('/browser-data/cookies', exist_ok=True)

    commands = [
        f'Xvfb {DISPLAY} -screen 0 {BROWSER_WINDOW_SIZE_WIDTH}x{BROWSER_WINDOW_SIZE_HEIGHT}x{SCREEN_COLOR_DEPTH_BITS} -ac',
        'fluxbox',
        f'x11vnc -display {DISPLAY} -nopw -forever -shared -reopen -bg -rfbport 5900',
        f'/opt/novnc/utils/novnc_proxy --vnc localhost:5900 --listen {NO_VNC_PORT}'
    ]

    try:
        for command in commands:
            logger.info(f"Executing {command}")
            p = await asyncio.create_subprocess_shell(
                command,
                stdout=sys.stdout,
                stderr=sys.stderr,
                shell=True,
                executable="/bin/bash"
            )
            processes.append(p)

        logger.info("Browser data directory status:")
        logger.info(f"Profile directory exists: {os.path.exists(BROWSER_PROFILE_DIR)}")
        logger.info(f"Cookies directory exists: {os.path.exists('/browser-data/cookies')}")

        # user_data_dir = "/browser-data/profiles/persistent"

        # Clean up any existing Chrome processes
        cleanup_cmd = "pkill -f chromium || true"
        process = await asyncio.create_subprocess_shell(
            cleanup_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

        playwright = await async_playwright().start()

        # browser = await playwright.chromium.launch_persistent_context(
        #     user_data_dir=user_data_dir,
        #     headless=False,
        #     args=[
        #         f"--window-size={BROWSER_WINDOW_SIZE_WIDTH},{BROWSER_WINDOW_SIZE_HEIGHT}",
        #         "--window-position=0,0",
        #         "--homepage=https://www.amazon.com",
        #         "--no-sandbox",
        #         "--disable-dev-shm-usage",
        #         "--disable-gpu",
        #         "--disable-software-rasterizer",
        #         "--disable-extensions",
        #         "--disable-default-apps",
        #         "--no-first-run",
        #         "--no-default-browser-check",
        #         "--password-store=basic",
        #         "--use-mock-keychain",
        #         "--disable-background-networking",
        #         "--disable-background-timer-throttling",
        #         "--disable-backgrounding-occluded-windows",
        #         "--disable-breakpad",
        #         "--disable-client-side-phishing-detection",
        #         "--disable-component-extensions-with-background-pages",
        #         "--disable-features=TranslateUI,BlinkGenPropertyTrees",
        #         "--disable-ipc-flooding-protection",
        #         "--disable-renderer-backgrounding",
        #         "--enable-features=NetworkService,NetworkServiceInProcess",
        #         "--force-color-profile=srgb",
        #         "--metrics-recording-only",
        #         "--mute-audio"
        #     ],
        #     viewport={"width": BROWSER_WINDOW_SIZE_WIDTH, "height": BROWSER_WINDOW_SIZE_HEIGHT}
        # )

        browser_profile = BrowserProfile(headless=False, user_data_dir=None, allowed_domains=['*'])


        browser = BrowserSession(
            browser_profile=browser_profile, user_data_dir=BROWSER_PROFILE_DIR,
            config=BrowserConfig(
                headless=False,
                disable_security=False,
                new_context_config=BrowserContextConfig(
                    allowed_domains=["*google.com*"],
                    cookies_file=None,
                    maximum_wait_page_load_time=5,
                    disable_security=False,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
                    viewport=dict(
                        width=BROWSER_WINDOW_SIZE_WIDTH,
                        height=BROWSER_WINDOW_SIZE_HEIGHT
                    )
                )
            )
        )

        ctx = await browser.new_context() 

        # Open amazon.com on start
        # if browser.pages:
        #     page = browser.pages[0]
        #     await page.goto("https://www.amazon.com")
        # else:
        #     page = await browser.new_page()
        #     await page.goto("https://www.amazon.com")

        # logger.info("Browser context created successfully")

        # try:
        #     pages = await browser.pages()
        #     logger.info(f"Active pages in context: {len(pages)}")
        # except Exception as e:
        #     logger.error(f"Error checking pages: {e}")

        # ctx = await browser.new_context() 

        _GLOBALS['browser'] = browser
        _GLOBALS['browser_context'] = ctx

        await _GLOBALS['browser_context'].__aenter__()
        yield

    except Exception as err:
        logger.error(f"Exception raised {err}", stack_info=True)

    finally:
        for process in processes:
            try:
                process.kill()
            except: pass

        if _GLOBALS.get('browser_context'):
            try:
                await _GLOBALS['browser_context'].__aexit__(None, None, None)
            except Exception as err:
                logger.error(f"Exception raised while closing browser context: {err}", stack_info=True)

        if _GLOBALS.get('playwright'):
            try:
                await _GLOBALS['playwright'].stop()
            except Exception as err:
                logger.error(f"Exception raised while stopping playwright: {err}", stack_info=True)

        # Final cleanup of Chrome processes
        cleanup_cmd = "pkill -f chromium || true"
        process = await asyncio.create_subprocess_shell(
            cleanup_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()

async def stream_reader(s: AsyncGenerator[Union[str, bytes], None]):
    error_message = None
    response_uuid = str(uuid.uuid4())

    try:
        async for chunk in s:
            if chunk is None:
                continue

            if isinstance(chunk, str):
                chunk_model = ChatCompletionStreamResponse(
                    id=response_uuid,
                    object='chat.completion.chunk',
                    created=int(time.time()),
                    model='unspecified',
                    choices=[
                        dict(
                            index=0,
                            delta=dict(
                                content=chunk,
                                role='assistant'
                            )
                        )
                    ]
                )

                yield (f'data: {chunk_model.model_dump_json()}\n\n').encode('utf-8')
            else:
                yield chunk

    except openai.APIConnectionError as e:
        error_message=f"Failed to connect to language model: {e}"

    except openai.RateLimitError as e:
        error_message=f"Rate limit error: {e}"

    except openai.APIError as e:
        error_message=f"Language model returned an API Error: {e}"

    except Exception as err:
        error_message = "Unhandled error: " + str(err)
        import traceback
        logger.error(traceback.format_exc())

    finally:
        if error_message:
            yield (f'data: {PromptErrorResponse(message=error_message).model_dump_json()}\n\n').encode('utf-8')

        yield b'data: [DONE]\n\n'

def main():
    api_app = fastapi.FastAPI(
        lifespan=lifespan
    )

    @api_app.get("/processing-url")
    async def get_processing_url():
        http_display_url = os.getenv("HTTP_DISPLAY_URL", "http://localhost:6080/vnc.html?host=localhost&port=6080")

        if http_display_url:
            return JSONResponse(
                content={
                    "url": http_display_url,
                    "status": "ready"
                },
                status_code=200
            )

        return JSONResponse(
            content={
                "status": "not ready"
            },
            status_code=404
        )

    @api_app.post("/prompt", response_model=None)
    async def post_prompt(body: dict) -> Union[StreamingResponse, PlainTextResponse, JSONResponse]:
        if body.get('ping'):
            return PlainTextResponse("online")

        messages: list[dict[str, str]] = body.pop('messages', [])

        if len(messages) == 0:
            return JSONResponse(
                content=PromptErrorResponse(
                    message="Received empty messages"
                ).model_dump(),
                status_code=400
            )

        if isinstance(messages[-1], str):
            messages[-1] = {
                "role": "user",
                "content": messages[-1]
            }

        messages[-1].setdefault('role', 'user')

        try:
            stream = prompt(
                messages, 
                browser_context=_GLOBALS["browser_context"], 
                **body
            )

            return StreamingResponse(
                stream_reader(stream),
                media_type="text/event-stream"
            )
        except Exception as err:
            error_message = "Unexpected Error: " + str(err)
            import traceback
            logger.error(traceback.format_exc())

            return JSONResponse(
                content=PromptErrorResponse(
                    message=error_message
                ).model_dump(),
                status_code=500
            )

    api_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)

    config = uvicorn.Config(
        api_app,
        loop=event_loop,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "80")),
        log_level="info",
        timeout_keep_alive=300,
    )

    server = uvicorn.Server(config)
    event_loop.run_until_complete(server.serve())

if __name__ == '__main__':
    main()
