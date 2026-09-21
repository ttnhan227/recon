from __future__ import annotations

import re
import threading
from typing import Any


class StatePool:
    """Thread-safe runtime state store for DAG dependency chaining and entity propagation."""

    _instance: StatePool | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._store: dict[str, list[str]] = {
            "id": [],
            "accountId": [],
            "customerId": [],
            "transactionId": [],
            "batchId": [],
            "runId": [],
            "userId": [],
        }
        self.auth_token: str | None = None

    @classmethod
    def get_instance(cls) -> StatePool:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def reset(self) -> None:
        with self._lock:
            for k in self._store:
                self._store[k].clear()
            self.auth_token = None

    def store_entity(self, key: str, value: str) -> None:
        if not value or not isinstance(value, str):
            return
        if (
            value.startswith("00000000-0000")
            or value.startswith("synthetic_")
            or value == "test_val"
        ):
            return

        norm_key = key.lower().replace("_", "").replace("-", "")
        with self._lock:
            # Store in specific normalized key list
            if norm_key not in self._store:
                self._store[norm_key] = []
            if value not in self._store[norm_key]:
                self._store[norm_key].insert(0, value)

            # Store in predefined specific keys
            for registered_key in self._store:
                if registered_key == "id":
                    continue
                reg_norm = registered_key.lower().replace("_", "").replace("-", "")
                if reg_norm == norm_key or reg_norm in norm_key or norm_key in reg_norm:
                    if value not in self._store[registered_key]:
                        self._store[registered_key].insert(0, value)

            # Fallback collection
            if value not in self._store["id"]:
                self._store["id"].insert(0, value)

    def get_latest(self, key: str) -> str | None:
        norm_key = key.lower().replace("_", "").replace("-", "")
        with self._lock:
            # If directly requesting generic "id", return latest from id pool
            if norm_key == "id":
                return self._store["id"][0] if self._store.get("id") else None

            # 1. Exact match on non-"id" keys
            for registered_key, values in self._store.items():
                if registered_key == "id":
                    continue
                reg_norm = registered_key.lower().replace("_", "").replace("-", "")
                if reg_norm == norm_key and values:
                    return values[0]

            # 2. Substring match on specific non-"id" keys
            for registered_key, values in self._store.items():
                if registered_key == "id":
                    continue
                reg_norm = registered_key.lower().replace("_", "").replace("-", "")
                if (reg_norm in norm_key or norm_key in reg_norm) and values:
                    return values[0]

            # 3. Fallback to generic "id"
            if self._store.get("id"):
                return self._store["id"][0]
        return None

    def get_all(self, key: str) -> list[str]:
        norm_key = key.lower().replace("_", "").replace("-", "")
        with self._lock:
            if norm_key == "id":
                return list(self._store.get("id", []))

            for registered_key, values in self._store.items():
                if registered_key == "id":
                    continue
                reg_norm = registered_key.lower().replace("_", "").replace("-", "")
                if reg_norm == norm_key and values:
                    return list(values)

            for registered_key, values in self._store.items():
                if registered_key == "id":
                    continue
                reg_norm = registered_key.lower().replace("_", "").replace("-", "")
                if (reg_norm in norm_key or norm_key in reg_norm) and values:
                    return list(values)

            return list(self._store.get("id", []))

    def harvest(self, data: Any) -> None:
        """Recursively harvests IDs and tokens from JSON response structures."""
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    self.harvest(v)
                elif isinstance(v, (str, int)):
                    v_str = str(v)
                    k_lower = k.lower()
                    if "token" in k_lower or "jwt" in k_lower:
                        self.auth_token = v_str
                    elif any(
                        id_keyword in k_lower
                        for id_keyword in (
                            "id",
                            "account",
                            "customer",
                            "transaction",
                            "batch",
                            "run",
                            "user",
                        )
                    ):
                        self.store_entity(k, v_str)
        elif isinstance(data, list):
            for item in data:
                self.harvest(item)

    def substitute_url(self, url: str) -> str:
        """Substitutes path params and placeholder GUIDs with real harvested entities."""
        # 1. Substitute {paramName}
        for param_match in re.findall(r"\{([a-zA-Z0-9_]+)\}", url):
            latest_val = self.get_latest(param_match)
            if latest_val:
                url = url.replace(f"{{{param_match}}}", latest_val)

        # 2. Substitute synthetic dummy GUIDs (00000000-0000-0000-0000-000000000001)
        if "00000000-0000-0000-0000-000000000001" in url:
            latest_id = self.get_latest("id")
            if latest_id:
                url = url.replace("00000000-0000-0000-0000-000000000001", latest_id)

        return url

    def substitute_payload(self, payload: Any) -> Any:
        """Substitutes payload references with real harvested entities."""
        if not isinstance(payload, dict):
            return payload

        mutated = dict(payload)
        for k, v in mutated.items():
            k_lower = k.lower()
            if isinstance(v, dict):
                mutated[k] = self.substitute_payload(v)
            elif isinstance(v, list):
                mutated[k] = [self.substitute_payload(item) for item in v]
            elif isinstance(v, str):
                # E.g. sourceAccountId, destinationAccountId, customerId
                if "source" in k_lower or "from" in k_lower:
                    accounts = self.get_all("accountId")
                    if accounts:
                        mutated[k] = accounts[0]
                elif "dest" in k_lower or "to" in k_lower or "target" in k_lower:
                    accounts = self.get_all("accountId")
                    if len(accounts) > 1:
                        mutated[k] = accounts[1]
                    elif accounts:
                        mutated[k] = accounts[0]
                elif "customer" in k_lower:
                    cust_id = self.get_latest("customerId")
                    if cust_id:
                        mutated[k] = cust_id
                elif "account" in k_lower:
                    acc_id = self.get_latest("accountId")
                    if acc_id:
                        mutated[k] = acc_id

        return mutated
