from browser_use import Agent
import logging
import asyncio
from typing import Optional
from browser_use.browser.context import BrowserContext


logger = logging.getLogger()


async def check_authorization(ctx: BrowserContext) -> bool:
    # check local storage for key 'polymarket.auth.params'
    local_storage = await ctx.session.context.local_storage('https://polymarket.com')
    auth_params = local_storage.get('polymarket.auth.params', None)

    # check if auth_params is not None and it object has value connectionState: 'ready'
    if auth_params is not None:
        connection_state = auth_params.get('connectionState', None)
        if connection_state == 'ready':
            return True
    return False




    # cookies = await ctx.session.context.cookies('https://mail.google.com')

    # for cookie in cookies:
        
    #     name = cookie.get('name', '')
    #     value = cookie.get('value', '')

    #     if name == 'SID' and value != '':
    #         return True

    # return False

async def ensure_url(ctx: BrowserContext, url: str) -> None:
    page = await ctx.get_current_page()
    current_url = page.url

    if not fnmatch(current_url, url + '*'):
        logger.info(f'Navigating to {url} from {current_url}')
        await page.goto(url, wait_until='networkidle')


async def on_task_start(agent: Agent) -> Agent: 
    logger.info("on_agent_start: reached")
    return agent

async def on_task_completed(agent: Agent) -> Agent:
    logger.info("on_task_completed: reached")
    # custom your logic here
    return agent
