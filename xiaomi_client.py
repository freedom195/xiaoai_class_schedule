# -*- coding: utf-8 -*-
"""
Xiaomi speaker client — wraps miservice-fork for TTS and conversation polling.

Login strategy based on xiaomusic (https://github.com/hanxi/xiaomusic):
  1. Pre-load passToken from .mi.auth (survives .mi.token deletion by library)
  2. Call mi_account.login("micoapi") directly — if passToken is valid,
     login succeeds WITHOUT password auth, bypassing notificationUrl entirely
  3. If login fails, retry with a fresh aiohttp session
  4. If still fails, detect notificationUrl for UI display
  5. Support cookie-based login (passToken + userId from browser) as alternative
  6. _patch_account wraps mi_request for runtime auto-recovery
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Optional, Dict, List

import aiohttp
from miservice import MiAccount, MiNAService
from miservice.miaccount import get_random

from config import decrypt, encrypt
from database import Session, get_config, set_config

logger = logging.getLogger(__name__)

from database import DATA_DIR

TOKEN_FILE = DATA_DIR / ".mi.token"
AUTH_FILE = DATA_DIR / ".mi.auth"  # passToken/userId/deviceId — survives .mi.token deletion
DEVICE_ID_FILE = DATA_DIR / ".mi_device_id"  # backwards compat
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
        self._last_error: str = ""  # last login error message for UI display
        self._verify_url: str = ""  # Xiaomi identity verification URL if needed

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    @property
    def last_error(self) -> str:
        """Return the last login error message (empty string if none)."""
        return self._last_error

    @property
    def verify_url(self) -> str:
        """Return the Xiaomi identity verification URL if login requires it."""
        return self._verify_url

    # ------------------------------------------------------------------
    # Persistent auth file (.mi.auth) — stores passToken/userId/deviceId
    # separately from .mi.token. The miservice library deletes .mi.token
    # on login failure (self.token = None → save_token() with no arg),
    # but .mi.auth is never touched by the library, so passToken survives.
    # ------------------------------------------------------------------

    @staticmethod
    def _load_auth() -> dict:
        """Load saved auth data (passToken/userId/deviceId) from .mi.auth."""
        try:
            if AUTH_FILE.exists():
                return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    @staticmethod
    def _save_auth(token: dict):
        """Save passToken/userId/deviceId to .mi.auth after successful login."""
        try:
            AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
            auth_data = {
                "passToken": token.get("passToken", ""),
                "userId": token.get("userId", ""),
                "deviceId": token.get("deviceId", ""),
            }
            AUTH_FILE.write_text(json.dumps(auth_data, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Could not save auth file: %s", e)

    @staticmethod
    def _load_persisted_device_id() -> str:
        """Load persisted deviceId from .mi_device_id (backwards compat)."""
        try:
            if DEVICE_ID_FILE.exists():
                return DEVICE_ID_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def _save_persisted_device_id(device_id: str):
        """Persist deviceId to .mi_device_id."""
        try:
            DEVICE_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
            DEVICE_ID_FILE.write_text(device_id, encoding="utf-8")
        except Exception as e:
            logger.warning("Could not save deviceId: %s", e)

    @staticmethod
    def _get_persisted_device_id() -> str:
        """Get deviceId from .mi.auth or .mi_device_id, generating new if needed."""
        auth = XiaomiClient._load_auth()
        did = auth.get("deviceId", "")
        if did:
            return did
        did = XiaomiClient._load_persisted_device_id()
        if did:
            return did
        return ""

    # ------------------------------------------------------------------
    # Core login — based on xiaomusic's AuthManager.login_miboy
    # ------------------------------------------------------------------

    async def login(self, account: str, password: str, force_reauth: bool = False) -> bool:
        """Authenticate with Xiaomi account.

        Uses mi_account.login("micoapi") directly. Before calling login(),
        we pre-load passToken from .mi.auth so that if it's still valid,
        the server returns code=0 at the serviceLogin handshake step —
        completely bypassing password auth and the notificationUrl issue.

        If login fails (passToken expired, wrong password, notificationUrl),
        we retry with a fresh aiohttp session. If that also fails, we
        manually detect notificationUrl for UI display.
        """
        await self._ensure_session()
        self._last_error = ""
        self._verify_url = ""

        # Ensure we have a deviceId — persist it so SMS verification survives
        device_id = self._get_persisted_device_id()
        if not device_id:
            device_id = get_random(16).upper()
            self._save_persisted_device_id(device_id)
            logger.info("Generated new deviceId: %s", device_id)

        # Attempt 1: login with current session
        login_ok = await self._try_login(account, password, device_id, self._session)
        if login_ok:
            return True

        logger.info("Login failed with current session, trying fresh session...")

        # Attempt 2: login with a brand new session (like xiaomusic's
        # _try_fresh_session_and_relogin)
        login_ok = await self._try_fresh_session_login(account, password, device_id)
        if login_ok:
            return True

        # Both attempts failed — detect notificationUrl for UI display
        await self._detect_notification_url(account, password, device_id)
        return False

    async def _try_login(
        self, account: str, password: str, device_id: str,
        session: aiohttp.ClientSession,
    ) -> bool:
        """Try login with a given session. Returns True on success."""
        try:
            mi_account = MiAccount(
                session, account, password, str(TOKEN_FILE)
            )
            self._set_token(mi_account, device_id)

            login_ok = await mi_account.login("micoapi")
            if not login_ok:
                logger.warning("mi_account.login returned False")
                return False

            # Success — set up services
            self._mi_account = mi_account
            self._mina = MiNAService(mi_account)
            self._patch_account(mi_account)

            # Save auth data for future logins (passToken survives .mi.token deletion)
            token = mi_account.token or {}
            self._save_auth(token)
            did = token.get("deviceId", device_id)
            if did:
                self._save_persisted_device_id(did)

            logger.info("Xiaomi login successful")
            return True

        except Exception as e:
            logger.error("Login attempt error: %s", e)
            return False

    async def _try_fresh_session_login(
        self, account: str, password: str, device_id: str,
    ) -> bool:
        """Retry login with a fresh aiohttp session (from xiaomusic)."""
        old_session = self._session
        try:
            new_session = aiohttp.ClientSession()
            result = await self._try_login(account, password, device_id, new_session)
            if result:
                # Replace old session with the new one
                if old_session and not old_session.closed:
                    await old_session.close()
                self._session = new_session
                logger.info("Fresh session login successful")
                return True
            else:
                await new_session.close()
                return False
        except Exception as e:
            logger.error("Fresh session login error: %s", e)
            return False

    def _set_token(self, mi_account: MiAccount, device_id: str):
        """Pre-load token before login (like xiaomusic's set_token).

        If .mi.token exists and has passToken, the library already loaded it.
        If not, we load passToken from .mi.auth so the server can recognize
        the session without requiring password auth.
        """
        if not mi_account.token:
            # .mi.token doesn't exist or was deleted — try .mi.auth
            auth = self._load_auth()
            if auth.get("passToken") and auth.get("userId"):
                mi_account.token = {
                    "passToken": auth["passToken"],
                    "userId": auth["userId"],
                    "deviceId": auth.get("deviceId", device_id),
                }
                logger.info(
                    "Pre-loaded passToken from .mi.auth (userId=%s)",
                    auth["userId"],
                )
            else:
                mi_account.token = {"deviceId": device_id}
                logger.info("No saved passToken, will use password auth")
        else:
            # .mi.token exists — ensure deviceId is set
            if "deviceId" not in mi_account.token:
                mi_account.token["deviceId"] = device_id

    def _patch_account(self, mi_account: MiAccount):
        """Wrap mi_request for auto-recovery (from xiaomusic's _patch_account).

        When a request fails with auth error, clear cookies, reload passToken
        from .mi.auth, re-login, and retry the original request.
        """
        original_mi_request = mi_account.mi_request
        client = self

        async def patched_mi_request(sid, url, data, headers, relogin=True):
            try:
                return await original_mi_request(sid, url, data, headers, relogin)
            except Exception as exc:
                if not relogin:
                    raise
                logger.warning("mi_request failed: %s, trying relogin...", exc)

                # Clear cookies and reload token
                mi_account.session.cookie_jar.clear()
                device_id = client._get_persisted_device_id()
                client._set_token(mi_account, device_id)

                if mi_account.token and "passToken" in mi_account.token:
                    try:
                        login_ok = await mi_account.login(sid)
                        if login_ok:
                            logger.info("Relogin successful, retrying request")
                            client._save_auth(mi_account.token or {})
                            return await original_mi_request(
                                sid, url, data, headers, False
                            )
                    except Exception as e2:
                        logger.warning("Relogin failed: %s", e2)
                raise

        mi_account.mi_request = patched_mi_request

    async def _detect_notification_url(
        self, account: str, password: str, device_id: str,
    ):
        """Fallback: manually detect notificationUrl when login fails.

        The library's login() catches all exceptions and returns False, so
        we can't get the notificationUrl from it. This method manually calls
        the login flow steps to extract it for UI display.
        """
        try:
            await self._ensure_session()
            mi_account = MiAccount(self._session, account, password, str(TOKEN_FILE))
            mi_account.token = {"deviceId": device_id}

            resp = await mi_account._serviceLogin(
                "serviceLogin?sid=micoapi&_json=true"
            )

            if resp.get("code") == 0:
                # Token actually works — shouldn't happen here, but handle it
                self._mi_account = mi_account
                self._mina = MiNAService(mi_account)
                self._patch_account(mi_account)
                self._last_error = ""
                logger.info("Login succeeded during notificationUrl detection")
                return

            data = {
                "_json": "true",
                "qs": resp["qs"],
                "sid": resp["sid"],
                "_sign": resp["_sign"],
                "callback": resp["callback"],
                "user": account,
                "hash": hashlib.md5(password.encode()).hexdigest().upper(),
            }
            resp = await mi_account._serviceLogin("serviceLoginAuth2", data)

            if resp.get("code") != 0:
                desc = resp.get("description", resp.get("desc", ""))
                if "70016" in str(resp) or "登录验证失败" in str(resp):
                    self._last_error = "登录验证失败：账号或密码错误，或账号已开启两步验证"
                elif desc:
                    self._last_error = f"登录失败：{desc}"
                else:
                    self._last_error = f"登录失败：{str(resp)[:200]}"
                return

            if "userId" not in resp:
                notif = resp.get("notificationUrl", "")
                if notif:
                    self._verify_url = (
                        notif if notif.startswith("http")
                        else "https://account.xiaomi.com" + notif
                    )
                    self._last_error = (
                        "小米账号需要安全验证。请在浏览器中打开验证链接，"
                        "完成短信验证后重新点击「保存并登录」。"
                        "也可使用 Cookie 方式登录（下方 Cookie 登录区域）。"
                    )
                    logger.info("Detected notificationUrl for security verification")
                else:
                    self._last_error = "登录失败：小米返回异常，请稍后重试"
            else:
                # Password auth succeeded but library login failed —
                # probably _securityTokenService failed. Complete it manually.
                logger.info("Password auth succeeded, completing login manually...")
                mi_account.token["userId"] = resp["userId"]
                mi_account.token["passToken"] = resp["passToken"]
                service_token = await mi_account._securityTokenService(
                    resp["location"], resp["nonce"], resp["ssecurity"]
                )
                mi_account.token["micoapi"] = (resp["ssecurity"], service_token)
                if mi_account.token_store:
                    mi_account.token_store.save_token(mi_account.token)
                self._mi_account = mi_account
                self._mina = MiNAService(mi_account)
                self._patch_account(mi_account)
                self._save_auth(mi_account.token)
                self._last_error = ""
                logger.info("Login completed via notificationUrl detection fallback")
                return

        except Exception as e:
            logger.error("notificationUrl detection error: %s", e)
            self._last_error = self._parse_login_error(e)

    # ------------------------------------------------------------------
    # Cookie-based login — alternative to password auth
    # ------------------------------------------------------------------

    async def login_with_cookies(
        self, pass_token: str, user_id: str,
    ) -> bool:
        """Login using passToken + userId from browser cookies.

        This completely bypasses password auth and the notificationUrl issue.
        The user gets passToken and userId from their browser cookies after
        logging into account.xiaomi.com, and we use them to login.

        Flow:
        1. Set token with passToken + userId + deviceId
        2. Call mi_account.login("micoapi") — passToken is sent as cookie,
           server returns code=0, login succeeds without password auth
        3. Fresh serviceToken is obtained via _securityTokenService
        """
        await self._ensure_session()
        self._last_error = ""
        self._verify_url = ""

        # Ensure deviceId
        device_id = self._get_persisted_device_id()
        if not device_id:
            device_id = get_random(16).upper()
            self._save_persisted_device_id(device_id)

        try:
            # Use placeholder account/password — login will use passToken
            mi_account = MiAccount(
                self._session, "", "", str(TOKEN_FILE)
            )
            mi_account.token = {
                "passToken": pass_token,
                "userId": user_id,
                "deviceId": device_id,
            }

            login_ok = await mi_account.login("micoapi")
            if not login_ok:
                # Try fresh session
                old_session = self._session
                new_session = aiohttp.ClientSession()
                mi_account2 = MiAccount(
                    new_session, "", "", str(TOKEN_FILE)
                )
                mi_account2.token = {
                    "passToken": pass_token,
                    "userId": user_id,
                    "deviceId": device_id,
                }
                login_ok = await mi_account2.login("micoapi")
                if login_ok:
                    if old_session and not old_session.closed:
                        await old_session.close()
                    self._session = new_session
                    mi_account = mi_account2
                else:
                    await new_session.close()
                    self._last_error = (
                        "Cookie 登录失败：passToken 可能已过期，"
                        "请重新从浏览器获取 Cookie"
                    )
                    return False

            self._mi_account = mi_account
            self._mina = MiNAService(mi_account)
            self._patch_account(mi_account)
            self._save_auth(mi_account.token or {})
            logger.info("Cookie login successful (userId=%s)", user_id)
            return True

        except Exception as e:
            logger.error("Cookie login failed: %s", e)
            self._last_error = f"Cookie 登录失败：{e}"
            self._mina = None
            return False

    @staticmethod
    def _parse_login_error(exc: Exception) -> str:
        """Parse the miservice login exception into a user-friendly message."""
        raw = str(exc)
        if "70016" in raw or "登录验证失败" in raw:
            return "登录验证失败：账号或密码错误，或账号已开启两步验证（需关闭）"
        if "KeyError" in raw and "userId" in raw:
            return "登录失败：小米要求安全验证，请使用 Cookie 方式登录"
        return raw[:200] if len(raw) > 200 else raw

    # ------------------------------------------------------------------
    # DB helpers
    # ------------------------------------------------------------------

    async def load_from_db(self, db_session: Session) -> bool:
        """Try to restore credentials from database and login.

        Prefers cookie-based login if passToken/userId are saved,
        falls back to password login.
        """
        # Try cookie-based login first (more reliable, bypasses notificationUrl)
        pass_token_enc = get_config(db_session, "mi_pass_token")
        user_id = get_config(db_session, "mi_user_id")
        if pass_token_enc and user_id:
            try:
                pass_token = decrypt(pass_token_enc)
                if await self.login_with_cookies(pass_token, user_id):
                    return True
                logger.warning(
                    "Cookie login from DB failed, falling back to password login"
                )
            except Exception as e:
                logger.warning("Cookie login from DB error: %s", e)

        # Fall back to password login
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

    async def save_cookies_to_db(
        self, db_session: Session, pass_token: str, user_id: str,
    ):
        """Save cookie-based auth credentials to database."""
        set_config(db_session, "mi_pass_token", encrypt(pass_token))
        set_config(db_session, "mi_user_id", user_id)

    # ------------------------------------------------------------------
    # Device / TTS / conversation — unchanged from original
    # ------------------------------------------------------------------

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

        The conversation API's `timestamp` parameter means "return records
        BEFORE this time" (not after). So we always pass the current time to
        get the most recent records, then use _last_ask_timestamp for local
        dedup: only return a record whose time is newer than the last one we
        handed back.
        """
        if not self._mina or not self._session or not self._mi_account:
            return None
        try:
            hardware = await self._get_hardware(device_id)
            now_ms = int(time.time() * 1000)
            url = LATEST_ASK_API.format(hardware=hardware, timestamp=now_ms)

            token = self._mi_account.token
            if not token:
                logger.warning("get_latest_conversation: no token, not logged in")
                return None
            cookies = {
                "userId": str(token["userId"]),
                "serviceToken": token["micoapi"][1],
                "deviceId": device_id,
            }
            headers = {
                "User-Agent": "MiHome/6.0.103 (com.xiaomi.mihome; build:6.0.103.1; iOS 14.4.0) Alamofire/6.0.103 MICO/iOSApp/appStore/6.0.103"
            }

            async with self._session.get(
                url, cookies=cookies, headers=headers,
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp:
                if resp.status != 200:
                    logger.warning("conversation API status=%s", resp.status)
                    return None
                data = await resp.json(content_type=None)

            code = data.get("code", -1)
            if code != 0:
                logger.warning("conversation API code=%s msg=%s", code, data.get("message"))
                return None

            inner = data.get("data")
            if isinstance(inner, str):
                inner = json.loads(inner)
            if not isinstance(inner, dict):
                return None

            records = inner.get("records", [])
            if not records:
                return None

            latest = records[0]
            ts = latest.get("time", 0)
            last_ts = self._last_ask_timestamp.get(device_id, 0)
            if ts <= last_ts:
                return None

            self._last_ask_timestamp[device_id] = ts
            query = latest.get("query", "")
            logger.info("New voice query from %s: %s", device_id, query)
            return query

        except Exception as e:
            logger.warning("get_latest_conversation error: %s", e)
            return None

    async def test_connection(self, device_id: str) -> dict:
        """Test connectivity — returns status dict with suggested devices on mismatch.

        Beyond listing devices, this also pings the target device with
        `player_get_status` so an offline / unreachable speaker is reported as
        failure. Without the live probe, a stale login token + a reachable
        account API would falsely report the speaker as "online".
        """
        if not self._mina:
            return {"ok": False, "error": "未登录，请先保存并登录"}
        devices = await self.get_device_list()
        matched = [d for d in devices if d.get("deviceID") == device_id]
        if not matched:
            ids = [{"deviceID": d.get("deviceID", ""), "name": d.get("name", "")} for d in devices]
            return {
                "ok": False,
                "error": f"未找到设备 {device_id}",
                "suggested_devices": ids,
            }
        try:
            status = await asyncio.wait_for(
                self._mina.player_get_status(device_id),
                timeout=6.0,
            )
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "error": "设备无响应（可能已离线或网络不通）",
                "device": matched[0],
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"设备不可达：{e}",
                "device": matched[0],
            }
        if not status:
            return {
                "ok": False,
                "error": "设备返回为空（可能已离线）",
                "device": matched[0],
            }
        return {"ok": True, "device": matched[0]}

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# Singleton used across the app
xiaomi_client = XiaomiClient()
