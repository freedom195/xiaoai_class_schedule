# -*- coding: utf-8 -*-
"""
Xiaomi speaker client — wraps miservice-fork for TTS and conversation polling.
Uses MiAccount + MiNAService from the miservice library.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, List

import aiohttp
from miservice import MiAccount, MiNAService

from config import decrypt, encrypt
from database import Session, get_config, set_config

logger = logging.getLogger(__name__)

from database import DATA_DIR

TOKEN_FILE = DATA_DIR / ".mi.token"
LATEST_ASK_API = (
    "https://userprofile.mina.mi.com/device_profile/v2/conversation"
    "?source=dialogu&hardware={hardware}&timestamp={timestamp}&limit=3"
)


class XiaomiClient:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._mi_account: Optional[MiAccount] = None
        self._mina: Optional[MiNAService] = None
        self._device_hardware: Dict[str, str] = {}  # device_id -> hardware type
        self._last_ask_timestamp: Dict[str, int] = {}  # device_id -> ms timestamp

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def login(self, account: str, password: str) -> bool:
        """Authenticate with Xiaomi account. Returns True on success."""
        await self._ensure_session()
        self._mi_account = MiAccount(
            self._session, account, password, str(TOKEN_FILE)
        )
        try:
            ok = await self._mi_account.login("micoapi")
            if ok:
                self._mina = MiNAService(self._mi_account)
                logger.info("Xiaomi login successful")
            return ok
        except Exception as e:
            logger.error("Xiaomi login failed: %s", e)
            return False

    async def load_from_db(self, db_session: Session) -> bool:
        """Try to restore credentials from database and login."""
        account_enc = get_config(db_session, "mi_account")
        password_enc = get_config(db_session, "mi_password")
        if not account_enc or not password_enc:
            return False
        try:
            account = decrypt(account_enc)
            password = decrypt(password_enc)
            return await self.login(account, password)
        except Exception as e:
            logger.error("Failed to load Xiaomi credentials: %s", e)
            return False

    async def save_to_db(self, db_session: Session, account: str, password: str):
        """Encrypt and save credentials to database."""
        set_config(db_session, "mi_account", encrypt(account))
        set_config(db_session, "mi_password", encrypt(password))

    async def get_device_list(self) -> List[Dict]:
        """Return list of available Xiaomi speakers."""
        if not self._mina:
            return []
        try:
            return await self._mina.device_list() or []
        except Exception as e:
            logger.error("get_device_list error: %s", e)
            return []

    async def _get_hardware(self, device_id: str) -> str:
        """Resolve hardware model for a device_id."""
        if device_id not in self._device_hardware:
            devices = await self.get_device_list()
            for d in devices:
                did = d.get("deviceID", "")
                hw = d.get("hardware", "")
                if did:
                    self._device_hardware[did] = hw
        return self._device_hardware.get(device_id, "")

    async def tts(self, device_id: str, text: str) -> bool:
        """Send text-to-speech to the speaker."""
        if not self._mina:
            logger.warning("TTS called but not logged in")
            return False
        try:
            await self._mina.text_to_speech(device_id, text)
            logger.info("TTS sent to %s: %s", device_id, text[:40])
            return True
        except Exception as e:
            logger.error("TTS error: %s", e)
            return False

    async def get_latest_conversation(self, device_id: str) -> Optional[str]:
        """
        Return the latest user utterance from the speaker, or None if no new message.
        Tracks timestamp so each call only returns messages newer than the last one.
        """
        if not self._mina or not self._session:
            return None
        try:
            hardware = await self._get_hardware(device_id)
            since_ts = self._last_ask_timestamp.get(device_id, int(time.time() * 1000) - 5000)
            url = LATEST_ASK_API.format(hardware=hardware, timestamp=since_ts)

            cookies = {}
            if hasattr(self._mi_account, "get_cookies"):
                cookies = await self._mi_account.get_cookies()

            async with self._session.get(url, cookies=cookies, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json(content_type=None)

            records = data.get("data", {}).get("records", [])
            if not records:
                return None

            latest = records[0]
            ts = latest.get("time", 0)
            if ts <= since_ts:
                return None

            self._last_ask_timestamp[device_id] = ts
            query = latest.get("query", "")
            logger.debug("New voice query from %s: %s", device_id, query)
            return query

        except Exception as e:
            logger.debug("get_latest_conversation error: %s", e)
            return None

    async def test_connection(self, device_id: str) -> dict:
        """Test connectivity — returns status dict with suggested devices on mismatch."""
        if not self._mina:
            return {"ok": False, "error": "未登录，请先保存并登录"}
        devices = await self.get_device_list()
        matched = [d for d in devices if d.get("deviceID") == device_id]
        if matched:
            return {"ok": True, "device": matched[0]}
        ids = [{"deviceID": d.get("deviceID", ""), "name": d.get("name", "")} for d in devices]
        return {
            "ok": False,
            "error": f"未找到设备 {device_id}",
            "suggested_devices": ids,
        }

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# Singleton used across the app
xiaomi_client = XiaomiClient()
