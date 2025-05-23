from browser_use import Controller, Browser, ActionResult
from .models import browser_use_custom_models
from browser_use.browser.context import BrowserContext
from .signals import (
    UnauthorizedAccess,
    RequireUserConfirmation
)
from typing import Literal
from fnmatch import fnmatch
import logging
from playwright._impl._api_structures import (
    ClientCertificate,
    Cookie
)
from typing import TypedDict


logger = logging.getLogger(__name__)

built_in_actions = [
    'done',
    'search_google',
    'go_to_url',
    'go_back',
    'wait',
    'click_element_by_index',
    'input_text',
    'save_pdf',
    'switch_tab',
    'open_tab',
    'close_tab',
    'extract_content',
    'scroll_down',
    'scroll_up',
    'send_keys',
    'scroll_to_text',
    'get_dropdown_options',
    'select_dropdown_option',
    'drag_drop',
    'get_sheet_contents',
    'select_cell_or_range',
    'get_range_contents',
    'clear_selected_range',
    'input_selected_cell_text',
    'update_range_contents' 
]

exclude = [
    a
    for a in built_in_actions
    if a not in [
        'done',
        # 'search_google',
        'go_to_url',
        'go_back',
        # 'wait',
        'click_element_by_index',
        'input_text',
        # 'save_pdf',
        # 'switch_tab',
        # 'open_tab',
        # 'close_tab',
        'extract_content',
        'scroll_down',
        'scroll_up',
        'send_keys',
        # 'scroll_to_text',

        'get_dropdown_options',
        'select_dropdown_option',

        # 'drag_drop',
        # 'get_sheet_contents',
        # 'select_cell_or_range',
        # 'get_range_contents',
        # 'clear_selected_range',
        # 'input_selected_cell_text',
        'update_range_contents' 
    ]
]

_controller = Controller(
    # output_model=browser_use_custom_models.FinalAgentResult,
    exclude_actions=exclude
)

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


async def ensure_url(ctx: BrowserContext, url: str) -> None:
    page = await ctx.get_current_page()
    current_url = page.url

    if not fnmatch(current_url, url):
        logger.info(f'Navigating to {url} from {current_url}')
        await page.goto(url, wait_until='networkidle')


def get_controler():
    global _controller
    return _controller