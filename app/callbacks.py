from browser_use import Agent
import logging

logger = logging.getLogger()

def on_task_start(agent: Agent) -> Agent: 
    logger.info("on_agent_start: reached")
    # custom your logic here
    return agent

def on_task_completed(agent: Agent) -> Agent:
    logger.info("on_task_completed: reached")
    # custom your logic here
    return agent
