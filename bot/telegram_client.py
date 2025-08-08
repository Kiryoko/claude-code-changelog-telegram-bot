from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

from telegram import Bot
from telegram.error import RetryAfter, TimedOut
from telegram.request import HTTPXRequest


TELEGRAM_MAX_LEN = 4096


def _truncate_message(text: str, max_len: int = TELEGRAM_MAX_LEN) -> str:
    if len(text) <= max_len:
        return text
    # Leave room for ellipsis
    return text[: max_len - 1] + "\u2026"


async def send_message(token: str, chat_id: str | int, text: str, max_retries: int = 3) -> None:
    logging.info(f"Sending message to {chat_id} (length: {len(text)} chars)")
    
    # Create bot with custom timeout settings
    request = HTTPXRequest(
        read_timeout=30,
        write_timeout=30,
        connect_timeout=10,
        pool_timeout=5
    )
    bot = Bot(token=token, request=request)
    truncated_text = _truncate_message(text)
    if len(truncated_text) != len(text):
        logging.warning(f"Message truncated from {len(text)} to {len(truncated_text)} chars")
    
    for attempt in range(max_retries + 1):
        try:
            await bot.send_message(chat_id=chat_id, text=truncated_text, parse_mode='Markdown')
            logging.info("Message sent successfully")
            return
        except RetryAfter as e:
            retry_after = e.retry_after
            if attempt < max_retries:
                logging.warning(f"Flood control exceeded. Waiting {retry_after} seconds before retry (attempt {attempt + 1}/{max_retries + 1})")
                await asyncio.sleep(retry_after + 1)  # Add 1 second buffer
            else:
                logging.error(f"Failed to send message after {max_retries + 1} attempts due to flood control")
                raise
        except TimedOut as e:
            if attempt < max_retries:
                backoff = 2 ** attempt  # Exponential backoff
                logging.warning(f"Request timed out. Waiting {backoff} seconds before retry (attempt {attempt + 1}/{max_retries + 1})")
                await asyncio.sleep(backoff)
            else:
                logging.error(f"Failed to send message after {max_retries + 1} attempts due to timeout")
                raise
        except Exception as e:
            logging.error(f"Failed to send message: {e}", exc_info=True)
            raise


async def get_last_sent_version(token: str, chat_id: str | int) -> Optional[str]:
    """
    Get the version from the last message sent to the channel.
    Returns None if no messages found or channel is empty.
    """
    # Create bot with custom timeout settings
    request = HTTPXRequest(
        read_timeout=30,
        write_timeout=30,
        connect_timeout=10,
        pool_timeout=5
    )
    bot = Bot(token=token, request=request)
    try:
        # For channels, we need to get chat info and then messages
        chat = await bot.get_chat(chat_id)
        logging.debug(f"Got chat info: {chat.type}")
        
        # Try to get the last few messages and find the latest one from our bot
        # We'll send a test message to get our own ID first
        try:
            bot_info = await bot.get_me()
            bot_username = bot_info.username
            logging.debug(f"Bot username: @{bot_username}")
            
            # Unfortunately, bots can't read channel message history directly
            # We'll have to rely on the database as the source of truth
            # But we can at least verify the bot has access to the channel
            await bot.get_chat_member_count(chat_id)
            logging.info("Bot has access to channel, will rely on database for resume logic")
            return None  # Let database handle the resume logic
            
        except Exception as e:
            logging.warning(f"Could not verify channel access or get bot info: {e}")
            return None
            
    except Exception as e:
        logging.error(f"Error checking channel: {e}")
        return None

