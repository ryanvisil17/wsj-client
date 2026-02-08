#!/usr/bin/env python3
"""
Generic Torrent Client - Search and Download via pluggable backends.

Supports multiple torrent clients through a unified interface:
  - rTorrent (ruTorrent XML-RPC)
  - qBittorrent (Web API)
  - Transmission (RPC)
  - Deluge (JSON-RPC)
  - aria2 (JSON-RPC)

Configuration via environment variables:
  TORRENT_CLIENT=rtorrent|qbittorrent|transmission|deluge|aria2
  TORRENT_URL=<backend_url>
  TORRENT_USER=<username>      (if required)
  TORRENT_PASSWORD=<password>  (if required)

Backend-specific defaults:
  - rTorrent:     http://vpn:8080/plugins/httprpc/action.php
  - qBittorrent:  http://localhost:8080
  - Transmission: http://localhost:9091/transmission/rpc
  - Deluge:       http://localhost:8112/json
  - aria2:        http://localhost:6800/jsonrpc

See docstrings for each client class for API details.
"""

import argparse
import os
import re
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote, urljoin
from xmlrpc.client import ServerProxy

import requests


def fetch_tracker_list() -> str:
    """
    Fetch the current tracker list from ThePirateBay's main.js.

    Returns:
        URL-encoded tracker string suitable for appending to magnet
            links. Returns empty string if fetch fails (degrades
            gracefully).
    """
    try:
        print("[1/3] Fetching tracker list from ThePirateBay...")
        response = requests.get(
            "https://thepiratebay.org/static/main.js", timeout=10
        )
        script_content = (
            response.text.replace(" ", "").replace("\n", "").replace("\t", "")
        )

        function_matches = re.findall(
            r"functionprint_trackers\(\){let([^}]*)returntr;}", script_content
        )

        if not function_matches:
            print(
                "  Warning: No tracker function found, continuing without trackers"
            )
            return ""

        trackers: list[str] = []
        for function_body in function_matches:
            for tracker_line in function_body.split(";"):
                if tracker_line.startswith("//"):
                    continue
                try:
                    tracker_url = tracker_line[
                        tracker_line.index("udp://") : tracker_line.rindex(
                            "')"
                        )
                    ]
                    trackers.append(tracker_url)
                except ValueError:
                    continue

        tracker_string = "".join(
            f"&tr={quote(tracker, safe=':/')}" for tracker in trackers
        )
        print(f"  Loaded {len(trackers)} trackers")
        return tracker_string

    except Exception as e:
        print(f"  Warning: Failed to fetch trackers: {e}")
        return ""


def search_magnet_link(query: str, exact_name: str | None = None) -> str:
    """
    Search ThePirateBay for a torrent and return its magnet link. The
    category is set to 601, for Ebooks

    Args:
        query: Search query string
        exact_name: Optional exact name to match (returns first result
            if None)

    Returns:
        Magnet link with trackers, or empty string if not found
    """
    try:
        print(f"[2/3] Searching ThePirateBay for: {query}")
        response = requests.get(
            "https://apibay.org/q.php",
            params={"q": query, "cat": 601},
            timeout=10,
        )

        if response.status_code != 200:
            print(f"  Error: Search failed with status {response.status_code}")
            return ""

        results = response.json()
        if not results or (isinstance(results, list) and len(results) == 0):
            print(f"  No results found for: {query}")
            return ""

        tracker_string = fetch_tracker_list()

        for result in results:
            if result.get("name") == "No results returned":
                continue

            result_name = result.get("name", "")
            info_hash = result.get("info_hash")

            if not info_hash:
                continue

            if exact_name and result_name == exact_name:
                magnet_link = f"magnet:?xt=urn:btih:{info_hash}&dn={quote(result_name)}{tracker_string}"
                print(f"  Found exact match: {result_name}")
                return magnet_link

            if not exact_name:
                magnet_link = f"magnet:?xt=urn:btih:{info_hash}&dn={quote(result_name)}{tracker_string}"
                print(f"  Found result: {result_name}")
                return magnet_link

        print("  No matching torrents found")
        return ""

    except Exception as e:
        print(f"  Error searching for magnet link: {e}")
        return ""


def extract_info_hash_from_magnet(magnet_link: str) -> Optional[str]:
    """
    Extract the BitTorrent info hash from a magnet link.

    Args:
        magnet_link: Magnet URI (magnet:?xt=urn:btih:...)

    Returns:
        Info hash string, or None if extraction fails
    """
    try:
        if "xt=urn:btih:" in magnet_link:
            start_idx = magnet_link.index("xt=urn:btih:") + len("xt=urn:btih:")
            end_idx = magnet_link.find("&", start_idx)
            return (
                magnet_link[start_idx:]
                if end_idx == -1
                else magnet_link[start_idx:end_idx]
            )
    except Exception:
        pass
    return None


@dataclass(frozen=True)
class TorrentHandle:
    """
    Backend-specific handle for tracking a torrent.

    The ID format varies by backend:
      - rTorrent:     40-char hex info_hash
      - qBittorrent:  40-char hex info_hash (lowercase)
      - Transmission: Numeric ID (as string)
      - Deluge:       40-char hex info_hash
      - aria2:        16-char GID (Global ID)
    """

    handle_id: str


@dataclass
class TorrentStatus:
    """Current status of a torrent download."""

    name: str = ""
    total_size_bytes: int = 0
    downloaded_bytes: int = 0
    is_complete: bool = False
    download_directory: str = ""


class TorrentClient(ABC):
    """
    Abstract base class for torrent client backends. All
    implementations must provide methods to add magnets and query
    status.
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
    ):
        self.base_url = base_url
        self.username = username
        self.password = password

    @abstractmethod
    def add_magnet_link(self, magnet_link: str) -> TorrentHandle:
        """
        Add a magnet link to the client and start downloading.

        Args:
            magnet_link: Magnet URI string

        Returns:
            TorrentHandle for polling status

        Raises:
            RuntimeError: If add fails
        """
        raise NotImplementedError

    @abstractmethod
    def get_torrent_status(self, handle: TorrentHandle) -> TorrentStatus:
        """
        Query current status of a torrent.

        Args:
            handle: TorrentHandle from add_magnet_link()

        Returns:
            TorrentStatus with current download state
        """
        raise NotImplementedError

    def wait_until_complete(
        self,
        handle: TorrentHandle,
        poll_interval_seconds: int = 10,
        timeout_seconds: int = 3600,
    ) -> Optional[Path]:
        """
        Poll torrent status until download completes or times out.

        Args:
            handle: TorrentHandle to monitor
            poll_interval_seconds: Time between status checks
            timeout_seconds: Maximum time to wait

        Returns:
            Path to downloaded file/directory, or None if timeout/error
        """
        print("  Waiting for download to complete...")
        elapsed_seconds = 0

        while elapsed_seconds < timeout_seconds:
            status = self.get_torrent_status(handle)

            if (
                not status.name
                and not status.total_size_bytes
                and not status.download_directory
            ):
                print(
                    "  Warning: Torrent not found (removed or backend error)"
                )
                return None

            if status.is_complete:
                print(f"\n  Download complete: {status.name}")
                if status.download_directory and status.name:
                    return Path(status.download_directory) / status.name
                if status.download_directory:
                    return Path(status.download_directory)
                return None

            if status.total_size_bytes > 0:
                progress_pct = (
                    status.downloaded_bytes / status.total_size_bytes
                ) * 100
                downloaded_mb = status.downloaded_bytes / 1_000_000
                total_mb = status.total_size_bytes / 1_000_000
                print(
                    f"  Progress: {progress_pct:.1f}% "
                    f"({downloaded_mb:.1f}MB / {total_mb:.1f}MB)",
                    end="\r",
                )

            time.sleep(poll_interval_seconds)
            elapsed_seconds += poll_interval_seconds

        print(f"\n  Error: Download timed out after {timeout_seconds} seconds")
        return None


class RTorrentClient(TorrentClient):
    """
    rTorrent client via ruTorrent's XML-RPC endpoint.

    API: XML-RPC over HTTP (basic auth optional)
    Default URL: http://vpn:8080/plugins/httprpc/action.php

    XML-RPC methods used:
      - load.start("", magnet_link) - Add and start torrent
      - d.name(hash) - Get torrent name
      - d.size_bytes(hash) - Get total size
      - d.completed_bytes(hash) - Get downloaded bytes
      - d.complete(hash) - Check if complete (1=yes)
      - d.directory(hash) - Get download directory
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
    ):
        if username and password:
            protocol, url_rest = base_url.split("://", 1)
            base_url = f"{protocol}://{username}:{password}@{url_rest}"

        super().__init__(base_url, username, password)
        self.rpc_server = ServerProxy(self.base_url)
        print(f"[3/3] Connected to rTorrent at: {base_url}")

    def add_magnet_link(self, magnet_link: str) -> TorrentHandle:
        info_hash = extract_info_hash_from_magnet(magnet_link)
        if not info_hash:
            raise RuntimeError("Failed to extract info hash from magnet link")

        try:
            self.rpc_server.load.start("", magnet_link)
            print("  Successfully added magnet to rTorrent")
        except Exception as e:
            print(f"  Error with primary method: {e}")
            print("  Trying alternative method...")
            self.rpc_server.load.start_verbose("", magnet_link)
            print("  Successfully added magnet using alternative method")

        return TorrentHandle(handle_id=info_hash)

    def get_torrent_status(self, handle: TorrentHandle) -> TorrentStatus:
        hash_id = handle.handle_id
        try:
            name = self.rpc_server.d.name(hash_id)
            total_size = int(self.rpc_server.d.size_bytes(hash_id))
            downloaded = int(self.rpc_server.d.completed_bytes(hash_id))
            is_complete = self.rpc_server.d.complete(hash_id) == 1
            directory = str(self.rpc_server.d.directory(hash_id))

            return TorrentStatus(
                name=name,
                total_size_bytes=total_size,
                downloaded_bytes=downloaded,
                is_complete=is_complete,
                download_directory=directory,
            )
        except Exception as e:
            print(f"\n  Error querying rTorrent: {e}")
            return TorrentStatus()


class QBittorrentClient(TorrentClient):
    """
    qBittorrent client via Web API (cookie-based auth).

    API: RESTful HTTP API with cookie authentication
    Default URL: http://localhost:8080
    Requires: WebUI enabled in qBittorrent settings

    Endpoints used:
      - POST /api/v2/auth/login - Authenticate and get cookie
      - POST /api/v2/torrents/add - Add magnet link
      - GET /api/v2/torrents/info?hashes=... - Query torrent status

    Docs: https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
    ):
        super().__init__(base_url.rstrip("/"), username, password)
        self.session = requests.Session()
        self._authenticate()
        print(f"[3/3] Connected to qBittorrent at: {self.base_url}")

    def _build_api_url(self, endpoint: str) -> str:
        """Build full API URL from endpoint path."""
        return urljoin(self.base_url + "/", endpoint.lstrip("/"))

    def _authenticate(self) -> None:
        """Authenticate with qBittorrent and obtain session cookie."""
        if not self.username or not self.password:
            raise RuntimeError(
                "qBittorrent requires TORRENT_USER and TORRENT_PASSWORD"
            )

        response = self.session.post(
            self._build_api_url("/api/v2/auth/login"),
            data={"username": self.username, "password": self.password},
            timeout=10,
        )

        if response.status_code != 200 or "Ok." not in response.text:
            raise RuntimeError(
                f"qBittorrent login failed: HTTP {response.status_code} "
                f"response={response.text!r}"
            )

    def add_magnet_link(self, magnet_link: str) -> TorrentHandle:
        info_hash = extract_info_hash_from_magnet(magnet_link)
        if not info_hash:
            raise RuntimeError("Failed to extract info hash from magnet link")

        response = self.session.post(
            self._build_api_url("/api/v2/torrents/add"),
            data={"urls": magnet_link},
            timeout=20,
        )

        if response.status_code != 200:
            raise RuntimeError(
                f"qBittorrent add failed: HTTP {response.status_code} "
                f"response={response.text!r}"
            )

        print("  Successfully added magnet to qBittorrent")
        return TorrentHandle(handle_id=info_hash.lower())

    def get_torrent_status(self, handle: TorrentHandle) -> TorrentStatus:
        response = self.session.get(
            self._build_api_url("/api/v2/torrents/info"),
            params={"hashes": handle.handle_id},
            timeout=10,
        )

        if response.status_code != 200:
            return TorrentStatus()

        torrents = response.json()
        if not torrents:
            return TorrentStatus()

        torrent_info = torrents[0]
        name = torrent_info.get("name", "") or ""
        total_size = int(torrent_info.get("size", 0) or 0)
        downloaded = int(torrent_info.get("completed", 0) or 0)
        progress = float(torrent_info.get("progress", 0.0) or 0.0)
        is_complete = progress >= 1.0
        directory = torrent_info.get("save_path", "") or ""

        return TorrentStatus(
            name=name,
            total_size_bytes=total_size,
            downloaded_bytes=downloaded,
            is_complete=is_complete,
            download_directory=directory,
        )


class TransmissionClient(TorrentClient):
    """
    Transmission client via JSON-RPC.

    API: JSON-RPC over HTTP with session ID handshake
    Default URL: http://localhost:9091/transmission/rpc
    Requires: RPC enabled in Transmission settings

    Special handling: Transmission requires X-Transmission-Session-Id
    header. First request returns 409 with correct session ID, then
    retry.

    RPC methods used:
      - torrent-add - Add magnet link
      - torrent-get - Query torrent status

    Docs: https://github.com/transmission/transmission/blob/main/docs/rpc-spec.md
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
    ):
        super().__init__(base_url, username, password)
        self.session = requests.Session()
        self.session_id: Optional[str] = None

        if self.username and self.password:
            self.session.auth = (self.username, self.password)

        print(f"[3/3] Connected to Transmission RPC at: {self.base_url}")

    def _execute_rpc(self, method: str, arguments: dict) -> dict:
        """
        Execute a Transmission RPC call with session ID handshake.

        Args:
            method: RPC method name
            arguments: Method arguments dict

        Returns:
            Response data dict

        Raises:
            RuntimeError: If RPC call fails
        """
        payload = {"method": method, "arguments": arguments}

        headers = {}
        if self.session_id:
            headers["X-Transmission-Session-Id"] = self.session_id

        response = self.session.post(
            self.base_url, json=payload, headers=headers, timeout=15
        )

        if response.status_code == 409:
            new_session_id = response.headers.get("X-Transmission-Session-Id")
            if not new_session_id:
                raise RuntimeError(
                    "Transmission returned 409 but no session ID header"
                )
            self.session_id = new_session_id
            headers["X-Transmission-Session-Id"] = self.session_id

            response = self.session.post(
                self.base_url, json=payload, headers=headers, timeout=15
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Transmission RPC failed: HTTP {response.status_code} "
                f"response={response.text!r}"
            )

        data = response.json()
        if data.get("result") != "success":
            raise RuntimeError(f"Transmission RPC error: {data!r}")

        return data

    def add_magnet_link(self, magnet_link: str) -> TorrentHandle:
        response_data = self._execute_rpc(
            "torrent-add", {"filename": magnet_link}
        )
        arguments = response_data.get("arguments", {})

        torrent_info = arguments.get("torrent-added") or arguments.get(
            "torrent-duplicate"
        )
        if not torrent_info or "id" not in torrent_info:
            raise RuntimeError(
                f"Unexpected Transmission response: {response_data!r}"
            )

        torrent_id = str(torrent_info["id"])
        print(f"  Successfully added magnet to Transmission (id={torrent_id})")
        return TorrentHandle(handle_id=torrent_id)

    def get_torrent_status(self, handle: TorrentHandle) -> TorrentStatus:
        torrent_id = int(handle.handle_id)
        response_data = self._execute_rpc(
            "torrent-get",
            {
                "ids": [torrent_id],
                "fields": [
                    "name",
                    "totalSize",
                    "haveValid",
                    "percentDone",
                    "isFinished",
                    "downloadDir",
                ],
            },
        )

        torrents = response_data.get("arguments", {}).get("torrents", [])
        if not torrents:
            return TorrentStatus()

        torrent = torrents[0]
        name = torrent.get("name", "") or ""
        total_size = int(torrent.get("totalSize", 0) or 0)
        downloaded = int(torrent.get("haveValid", 0) or 0)
        percent_done = float(torrent.get("percentDone", 0.0) or 0.0)
        is_finished = bool(torrent.get("isFinished"))
        is_complete = is_finished or percent_done >= 1.0
        directory = torrent.get("downloadDir", "") or ""

        return TorrentStatus(
            name=name,
            total_size_bytes=total_size,
            downloaded_bytes=downloaded,
            is_complete=is_complete,
            download_directory=directory,
        )


class DelugeClient(TorrentClient):
    """
    Deluge client via JSON-RPC (Web API).

    API: JSON-RPC over HTTP with cookie-based auth
    Default URL: http://localhost:8112/json
    Requires: Web UI enabled in Deluge settings

    RPC methods used:
      - auth.login - Authenticate with password
      - core.add_torrent_magnet - Add magnet link
      - core.get_torrent_status - Query status

    Docs: https://deluge.readthedocs.io/en/latest/reference/api.html
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
    ):
        super().__init__(base_url, username, password)
        self.session = requests.Session()
        self.request_id = 1
        self._authenticate()
        print(f"[3/3] Connected to Deluge at: {self.base_url}")

    def _execute_rpc(self, method: str, params: list) -> Any:
        """
        Execute a Deluge JSON-RPC call.

        Args:
            method: RPC method name
            params: List of method parameters

        Returns:
            Result from RPC response

        Raises:
            RuntimeError: If RPC call fails
        """
        payload = {
            "method": method,
            "params": params,
            "id": self.request_id,
        }
        self.request_id += 1

        response = self.session.post(self.base_url, json=payload, timeout=15)

        if response.status_code != 200:
            raise RuntimeError(
                f"Deluge RPC failed: HTTP {response.status_code} "
                f"response={response.text!r}"
            )

        data = response.json()
        if "error" in data and data["error"]:
            raise RuntimeError(f"Deluge RPC error: {data['error']!r}")

        return data.get("result")

    def _authenticate(self) -> None:
        """Authenticate with Deluge Web UI."""
        if not self.password:
            raise RuntimeError(
                "Deluge requires TORRENT_PASSWORD (default: 'deluge')"
            )

        result = self._execute_rpc("auth.login", [self.password])
        if not result:
            raise RuntimeError("Deluge authentication failed")

    def add_magnet_link(self, magnet_link: str) -> TorrentHandle:
        info_hash = extract_info_hash_from_magnet(magnet_link)
        if not info_hash:
            raise RuntimeError("Failed to extract info hash from magnet link")

        result_hash = self._execute_rpc(
            "core.add_torrent_magnet", [magnet_link, {}]
        )

        if not result_hash:
            raise RuntimeError("Deluge add_torrent_magnet returned None")

        print("  Successfully added magnet to Deluge")
        return TorrentHandle(handle_id=result_hash)

    def get_torrent_status(self, handle: TorrentHandle) -> TorrentStatus:
        fields = [
            "name",
            "total_size",
            "all_time_download",
            "progress",
            "is_finished",
            "save_path",
        ]

        status_dict = self._execute_rpc(
            "core.get_torrent_status", [handle.handle_id, fields]
        )

        if not status_dict:
            return TorrentStatus()

        name = status_dict.get("name", "") or ""
        total_size = int(status_dict.get("total_size", 0) or 0)
        downloaded = int(status_dict.get("all_time_download", 0) or 0)
        progress = float(status_dict.get("progress", 0.0) or 0.0)
        is_complete = bool(status_dict.get("is_finished")) or progress >= 100.0
        directory = status_dict.get("save_path", "") or ""

        return TorrentStatus(
            name=name,
            total_size_bytes=total_size,
            downloaded_bytes=downloaded,
            is_complete=is_complete,
            download_directory=directory,
        )


class Aria2Client(TorrentClient):
    """
    aria2 client via JSON-RPC.

    API: JSON-RPC 2.0 over HTTP (optional token auth)
    Default URL: http://localhost:6800/jsonrpc
    Requires: RPC enabled (--enable-rpc flag)

    Auth: Uses secret token in RPC params (if configured)
    Set TORRENT_PASSWORD to your aria2 RPC secret

    RPC methods used:
      - aria2.addUri - Add magnet link (returns GID)
      - aria2.tellStatus - Query download status

    Docs: https://aria2.github.io/manual/en/html/aria2c.html#rpc-interface
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
    ):
        super().__init__(base_url, username, password)
        self.session = requests.Session()
        self.request_id = 1

        self.token = f"token:{password}" if password else None

        print(f"[3/3] Connected to aria2 at: {self.base_url}")

    def _execute_rpc(self, method: str, params: list) -> Any:
        """
        Execute an aria2 JSON-RPC 2.0 call.

        Args:
            method: RPC method name (e.g., "aria2.addUri")
            params: List of method parameters

        Returns:
            Result from RPC response

        Raises:
            RuntimeError: If RPC call fails
        """
        if self.token:
            params = [self.token] + params

        payload = {
            "jsonrpc": "2.0",
            "id": str(self.request_id),
            "method": method,
            "params": params,
        }
        self.request_id += 1

        response = self.session.post(self.base_url, json=payload, timeout=15)

        if response.status_code != 200:
            raise RuntimeError(
                f"aria2 RPC failed: HTTP {response.status_code} "
                f"response={response.text!r}"
            )

        data = response.json()
        if "error" in data:
            raise RuntimeError(
                f"aria2 RPC error: {data['error'].get('message', data['error'])}"
            )

        return data.get("result")

    def add_magnet_link(self, magnet_link: str) -> TorrentHandle:
        gid = self._execute_rpc("aria2.addUri", [[magnet_link]])

        if not gid:
            raise RuntimeError("aria2 addUri returned no GID")

        print(f"  Successfully added magnet to aria2 (GID={gid})")
        return TorrentHandle(handle_id=gid)

    def get_torrent_status(self, handle: TorrentHandle) -> TorrentStatus:
        status_dict = self._execute_rpc(
            "aria2.tellStatus",
            [
                handle.handle_id,
                [
                    "gid",
                    "totalLength",
                    "completedLength",
                    "status",
                    "dir",
                    "bittorrent",
                ],
            ],
        )

        if not status_dict:
            return TorrentStatus()

        name = ""
        bittorrent_info = status_dict.get("bittorrent", {})
        if bittorrent_info and "info" in bittorrent_info:
            name = bittorrent_info["info"].get("name", "")

        total_size = int(status_dict.get("totalLength", 0) or 0)
        downloaded = int(status_dict.get("completedLength", 0) or 0)
        aria2_status = status_dict.get("status", "")
        is_complete = aria2_status == "complete"
        directory = status_dict.get("dir", "") or ""

        return TorrentStatus(
            name=name,
            total_size_bytes=total_size,
            downloaded_bytes=downloaded,
            is_complete=is_complete,
            download_directory=directory,
        )


def create_torrent_client(
    client_type: str, url: str, username: str | None, password: str | None
) -> TorrentClient:
    """
    Factory function to create the appropriate torrent client.

    Args:
        client_type: Client identifier (rtorrent, qbittorrent, etc.)
        url: Backend URL
        username: Optional username
        password: Optional password/token

    Returns:
        Initialized TorrentClient instance

    Raises:
        RuntimeError: If client_type is unsupported
    """
    client_type_lower = client_type.strip().lower()

    client_map = {
        "rtorrent": RTorrentClient,
        "rutorrent": RTorrentClient,
        "qbittorrent": QBittorrentClient,
        "qbit": QBittorrentClient,
        "qbt": QBittorrentClient,
        "transmission": TransmissionClient,
        "trans": TransmissionClient,
        "deluge": DelugeClient,
        "aria2": Aria2Client,
        "aria2c": Aria2Client,
    }

    client_class = client_map.get(client_type_lower)
    if not client_class:
        supported = ", ".join(
            sorted(set(client_map.values().__name__ for _ in client_map))
        )
        raise RuntimeError(
            f"Unsupported TORRENT_CLIENT='{client_type}'. "
            f"Supported: {supported}"
        )

    return client_class(base_url=url, username=username, password=password)


def main() -> None:
    """Main application entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description="Search torrents and download via multiple client backends",
        epilog="Supported clients: rTorrent, qBittorrent, Transmission, Deluge, aria2",
    )
    parser.add_argument("query", help="Search query for ThePirateBay")
    parser.add_argument("exact_name", help="Exact torrent name to match")
    parser.add_argument(
        "--torrent-url",
        default=os.getenv(
            "TORRENT_URL",
            os.getenv(
                "RTORRENT_URL", "http://vpn:8080/plugins/httprpc/action.php"
            ),
        ),
        help="Backend URL (varies by client type)",
    )
    parser.add_argument(
        "--torrent-user",
        default=os.getenv("TORRENT_USER", os.getenv("RTORRENT_USER")),
        help="Backend username (if required)",
    )
    parser.add_argument(
        "--torrent-password",
        default=os.getenv("TORRENT_PASSWORD", os.getenv("RTORRENT_PASSWORD")),
        help="Backend password/token (if required)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Status polling interval in seconds (default: 10)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="Download timeout in seconds (default: 3600)",
    )

    args = parser.parse_args()

    try:
        # Step 1-2: Search for magnet link
        magnet_link = search_magnet_link(args.query, args.exact_name)
        if not magnet_link:
            print("\nError: No magnet link found")
            sys.exit(1)

        # Step 3: Initialize client
        client_type = os.getenv("TORRENT_CLIENT", "rtorrent")
        client = create_torrent_client(
            client_type=client_type,
            url=args.torrent_url,
            username=args.torrent_user,
            password=args.torrent_password,
        )

        # Add magnet and wait for completion
        torrent_handle = client.add_magnet_link(magnet_link)
        download_path = client.wait_until_complete(
            torrent_handle,
            poll_interval_seconds=args.poll_interval,
            timeout_seconds=args.timeout,
        )

        if not download_path:
            print("\nError: Download failed or timed out")
            sys.exit(1)

        print(f"\n\nSuccess! Downloaded to: {download_path}")
        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
