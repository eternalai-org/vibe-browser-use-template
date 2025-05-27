from browser_use import Agent
import logging
import asyncio
from typing import Optional
from browser_use.browser.context import BrowserContext
from .controllers import check_authorization
from .signals import UnauthorizedAccess


logger = logging.getLogger()

async def require_login(agent: Agent) -> None:
    """Check if user is logged in and raise UnauthorizedAccess if not."""
    ctx = agent.browser_context
    is_authorized = await check_authorization(ctx)
    
    if not is_authorized:
        raise UnauthorizedAccess(
            "You need to login first. Please login to your Polymarket account, "
            "then let me know once you've completed the login process."
        )

async def on_task_start(agent: Agent) -> Agent:
    logger.info("on_agent_start: reached")
    # Check for login requirement at the start of each task
    try:
        await require_login(agent)
    except UnauthorizedAccess as e:
        # Let this exception bubble up - it will be caught and handled properly by the agent
        raise
        
    return agent

async def on_task_completed(agent: Agent) -> Agent:
    logger.info("on_task_completed: reached")
    return agent
