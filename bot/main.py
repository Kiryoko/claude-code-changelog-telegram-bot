from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import logging
import signal
import sys

import httpx

from .config import Config
from .db import Database
from .changelog import parse_changelog, ChangelogEntry
from .telegram_client import send_message, get_last_sent_version


def format_entry_message(entry: ChangelogEntry) -> str:
    title = f"*Claude Code v{entry.version}*"
    body = entry.body.strip()
    # Escape markdown special characters in body text to prevent parsing errors
    body = body.replace('_', '\\_').replace('*', '\\*').replace('`', '\\`').replace('[', '\\[').replace(']', '\\]')
    text = f"{title}\n\n{body}"
    return text.strip()


async def fetch_changelog(url: str) -> str:
    logging.info(f"Fetching changelog from {url}")
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        logging.info(f"Successfully fetched changelog ({len(resp.text)} chars)")
        return resp.text


# Global shutdown event
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logging.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


async def send_backlog_if_needed(cfg: Config, db: Database) -> None:
    logging.info("Processing backlog...")
    markdown = await fetch_changelog(cfg.changelog_url)
    entries = parse_changelog(markdown)
    logging.info(f"Parsed {len(entries)} changelog entries")
    # The file is newest-first; send backlog oldest-first
    entries.reverse()

    known = db.get_known_versions()
    logging.info(f"Found {len(known)} known versions in database")
    
    # First, ensure DB has all entries (but don't mark as sent)
    for e in entries:
        db.upsert_version(e.version, e.content_hash, e.body)

    # Get unsent versions (includes both new and previously failed sends)
    # Process them in chronological order from the changelog, not alphabetical DB order
    unsent_versions_set = set(db.get_unsent_versions())
    unsent_entries = [e for e in entries if e.version in unsent_versions_set]
    
    logging.info(f"Found {len(unsent_entries)} unsent entries to process")
    
    for i, e in enumerate(unsent_entries):
        # Check for shutdown signal before processing each message
        if shutdown_event.is_set():
            logging.info("Shutdown requested, stopping backlog processing")
            break
            
        logging.info(f"Sending message for version {e.version} ({i+1}/{len(unsent_entries)})")
        
        try:
            await send_message(cfg.telegram_token, cfg.telegram_chat_id, format_entry_message(e))
            # Only mark as sent AFTER successful send
            db.mark_posted(e.version, datetime.now(timezone.utc).isoformat())
            logging.info(f"Successfully sent and marked version {e.version} as sent")
        except Exception as e_error:
            logging.error(f"Failed to send message for version {e.version}: {e_error}")
            break  # Stop processing to avoid cascading failures
        
        # Add delay between messages to avoid flood control, but check for shutdown
        if i < len(unsent_entries) - 1:
            logging.debug("Waiting 2 seconds before next message...")
            # Sleep in smaller chunks to be responsive to shutdown
            for _ in range(20):  # 20 * 0.1 = 2 seconds
                if shutdown_event.is_set():
                    logging.info("Shutdown requested during delay, stopping")
                    break
                await asyncio.sleep(0.1)
    
    # Count how many we actually sent successfully
    remaining_unsent = db.get_unsent_versions() 
    sent_count = len(unsent_entries) - len([v for v in remaining_unsent if v in [e.version for e in unsent_entries]])
    if sent_count > 0:
        logging.info(f"Successfully sent {sent_count} messages")
    else:
        logging.info("No messages sent")


async def poll_for_updates(cfg: Config, db: Database) -> None:
    logging.info(f"Starting polling loop (interval: {cfg.poll_interval}s)")
    while not shutdown_event.is_set():
        try:
            logging.debug("Polling for updates...")
            markdown = await fetch_changelog(cfg.changelog_url)
            entries = parse_changelog(markdown)
            # newest-first per file structure
            if not entries:
                logging.warning("No entries found in changelog")
                await asyncio.sleep(cfg.poll_interval)
                continue
                
            known = db.get_known_versions()
            # Determine newly appeared versions by header, preserving chronological order
            chronological = list(reversed(entries))  # oldest -> newest
            new_versions = [e for e in chronological if e.version not in known]
            
            if new_versions:
                logging.info(f"Found {len(new_versions)} new versions: {[e.version for e in new_versions]}")
            else:
                logging.debug("No new versions found")

            # Upsert all parsed versions to DB (so we keep latest content hashes)
            for e in entries:
                db.upsert_version(e.version, e.content_hash, e.body)

            # Post newly discovered.
            for i, e in enumerate(new_versions):
                # Check for shutdown signal
                if shutdown_event.is_set():
                    logging.info("Shutdown requested, stopping new version processing")
                    break
                    
                logging.info(f"Sending update message for version {e.version}")
                
                try:
                    await send_message(cfg.telegram_token, cfg.telegram_chat_id, format_entry_message(e))
                    # Only mark as sent AFTER successful send
                    db.mark_posted(e.version, datetime.now(timezone.utc).isoformat())
                    logging.info(f"Successfully sent version {e.version}")
                except Exception as e_error:
                    logging.error(f"Failed to send message for version {e.version}: {e_error}")
                    # Version will remain unsent and be retried on next poll or restart
                
                # Add delay between messages to avoid flood control
                if i < len(new_versions) - 1:
                    logging.debug("Waiting 2 seconds before next message...")
                    # Sleep in smaller chunks to be responsive to shutdown
                    for _ in range(20):  # 20 * 0.1 = 2 seconds
                        if shutdown_event.is_set():
                            logging.info("Shutdown requested during delay, stopping")
                            break
                        await asyncio.sleep(0.1)

        except Exception as e:
            logging.error(f"Error in polling loop: {e}", exc_info=True)

        logging.debug(f"Sleeping for {cfg.poll_interval} seconds...")
        
        # Sleep with shutdown check - break into smaller chunks to be more responsive
        sleep_remaining = cfg.poll_interval
        while sleep_remaining > 0 and not shutdown_event.is_set():
            chunk = min(1.0, sleep_remaining)  # Sleep in 1-second chunks
            await asyncio.sleep(chunk)
            sleep_remaining -= chunk
    
    logging.info("Polling loop stopped due to shutdown signal")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('bot.log')
        ]
    )
    # Reduce httpx logging noise
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.INFO)


async def async_main() -> int:
    setup_logging()
    logging.info("Starting Claude Changelog Telegram Bot...")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    cfg = Config()
    try:
        cfg.validate()
        logging.info("Configuration validated successfully")
        logging.info(f"Changelog URL: {cfg.changelog_url}")
        logging.info(f"Poll interval: {cfg.poll_interval}s")
        logging.info(f"Database path: {cfg.database_path}")
        logging.info(f"Chat ID: {cfg.telegram_chat_id}")
    except Exception as e:
        logging.error(f"Configuration error: {e}")
        return 2

    db = Database(cfg.database_path)
    logging.info("Database initialized")

    # Verify channel access and get last sent version if possible
    try:
        last_version = await get_last_sent_version(cfg.telegram_token, cfg.telegram_chat_id)
        if last_version:
            logging.info(f"Last version found in channel: {last_version}")
    except Exception as e:
        logging.warning(f"Could not check last sent version: {e}")

    # Initial backlog processing
    try:
        await send_backlog_if_needed(cfg, db)
        if shutdown_event.is_set():
            logging.info("Shutdown requested during backlog processing")
            return 0
        logging.info("Backlog processing completed")
    except Exception as e:
        logging.error(f"Startup backlog error: {e}", exc_info=True)
        return 1

    # Poll forever (or until shutdown)
    logging.info("Entering polling loop...")
    await poll_for_updates(cfg, db)
    
    logging.info("Bot shutdown completed gracefully")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))
