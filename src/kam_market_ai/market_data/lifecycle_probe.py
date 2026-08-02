"""Bounded, non-persistent WebSocket lifecycle diagnostics only."""
from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from enum import StrEnum
from time import monotonic
from typing import Any

from fugle_marketdata.websocket.client import AuthenticationState
from ..models import SessionKind
from ..session import SessionEngine


class LifecycleFailureStage(StrEnum):
    CLIENT_INIT_FAILED="CLIENT_INIT_FAILED"; CALLBACK_REGISTRATION_FAILED="CALLBACK_REGISTRATION_FAILED"
    CONNECT_FAILED="CONNECT_FAILED"; CONNECTED_EVENT_TIMEOUT="CONNECTED_EVENT_TIMEOUT"; AUTH_NOT_READY="AUTH_NOT_READY"
    SUBSCRIBE_PAYLOAD_INVALID="SUBSCRIBE_PAYLOAD_INVALID"; SUBSCRIBE_FAILED="SUBSCRIBE_FAILED"
    SUBSCRIBE_ACK_TIMEOUT="SUBSCRIBE_ACK_TIMEOUT"; NO_MARKET_EVENT="NO_MARKET_EVENT"
    UNSUBSCRIBE_FAILED="UNSUBSCRIBE_FAILED"; DISCONNECT_FAILED="DISCONNECT_FAILED"; NONE="NONE"

@dataclass(frozen=True, slots=True)
class LifecycleStatus:
    client_created: bool; callbacks_registered: bool; connect_called: bool; connected_event_received: bool
    auth_status: str; subscribe_called: bool; subscribe_ack_received: bool; heartbeat_received: bool
    market_event_received: bool; tx_event_count: int; tmf_event_count: int; unsubscribe_success: bool; disconnect_success: bool
    failure_stage: LifecycleFailureStage; callback_event_names: tuple[str,...]; subscribe_payloads: tuple[dict[str,object],...]
    def safe_payload(self) -> dict[str, object]:
        payload=asdict(self); payload["failure_stage"]=self.failure_stage.value; return payload

class WebSocketLifecycleProbe:
    _non_ack=frozenset({"data","pong","authenticated","error"})
    @staticmethod
    def stock_subscription() -> dict[str,object]: return {"channel":"indices","symbol":"IR0001"}
    @staticmethod
    def futures_subscription(symbol: str, *, after_hours: bool=False) -> dict[str,object]:
        data={"channel":"trades","symbol":symbol}
        if after_hours: data["afterHours"]=True
        return data
    @staticmethod
    def session_aware_futures_subscription(symbol: str, session: SessionKind) -> dict[str, object]:
        if session is SessionKind.DAY:
            return WebSocketLifecycleProbe.futures_subscription(symbol, after_hours=False)
        if session is SessionKind.NIGHT:
            return WebSocketLifecycleProbe.futures_subscription(symbol, after_hours=True)
        raise ValueError("Session is not eligible for a futures subscription")
    def run(self, client: object, subscriptions: tuple[dict[str,object],...], *, duration_seconds: float=30) -> LifecycleStatus:
        required=("on","off","connect","subscribe","unsubscribe","disconnect")
        if client is None or any(not hasattr(client,n) for n in required): return self._empty(LifecycleFailureStage.CLIENT_INIT_FAILED)
        state={"connected":False,"authenticated":False,"unauthenticated":False,"heartbeat":False,"market":False,"ack":False,"subscribe":False,"unsub":True,"disconnect":True,"tx_count":0,"tmf_count":0}
        symbols=tuple(str(p.get("symbol")) for p in subscriptions if isinstance(p.get("symbol"),str))
        names: list[str]=[]; lock=threading.Lock()
        def mark(name: str) -> None:
            with lock:
                if name not in names: names.append(name)
        def connected() -> None: state["connected"]=True; mark("connect")
        def authenticated(_: object) -> None: state["authenticated"]=True; mark("authenticated")
        def unauthenticated(_: object) -> None: state["unauthenticated"]=True; mark("unauthenticated")
        def error(_: object) -> None: mark("error")
        def disconnected(*_: object) -> None: mark("disconnect")
        def message(value: str|Mapping[str,Any]) -> None:
            try: parsed=json.loads(value) if isinstance(value,str) else value
            except (TypeError,ValueError): return
            d=parsed.get("data",{}) if isinstance(parsed,Mapping) else {}
            name=parsed.get("event") if isinstance(parsed,Mapping) else None
            if name is None: return
            mark(name); state["heartbeat"] |= name=="pong"; state["market"] |= name=="data"
            if name=="data" and isinstance(d,Mapping):
                symbol=d.get("symbol")
                if len(symbols)>0 and symbol==symbols[0]: state["tx_count"]+=1
                elif len(symbols)>1 and symbol==symbols[1]: state["tmf_count"]+=1
            if name not in self._non_ack: state["ack"]=True
        listeners=(("connect",connected),("authenticated",authenticated),("unauthenticated",unauthenticated),("error",error),("disconnect",disconnected),("message",message))
        try:
            for event, listener in listeners: client.on(event,listener)
        except Exception:
            self._remove(client,listeners); return self._empty(LifecycleFailureStage.CALLBACK_REGISTRATION_FAILED)
        try: client.connect()
        except Exception: return self._finish(client,listeners,subscriptions,state,names,LifecycleFailureStage.CONNECT_FAILED,True)
        if not state["connected"]: return self._finish(client,listeners,subscriptions,state,names,LifecycleFailureStage.CONNECTED_EVENT_TIMEOUT,True)
        if getattr(client,"auth_status",None)!=AuthenticationState.AUTHENTICATED or not state["authenticated"]:
            return self._finish(client,listeners,subscriptions,state,names,LifecycleFailureStage.AUTH_NOT_READY,True)
        for params in subscriptions:
            if not isinstance(params.get("channel"),str) or not isinstance(params.get("symbol"),str):
                return self._finish(client,listeners,subscriptions,state,names,LifecycleFailureStage.SUBSCRIBE_PAYLOAD_INVALID,True)
            try: client.subscribe(params); state["subscribe"]=True
            except Exception: return self._finish(client,listeners,subscriptions,state,names,LifecycleFailureStage.SUBSCRIBE_FAILED,True)
        deadline=monotonic()+duration_seconds
        while monotonic()<deadline: threading.Event().wait(min(.1,deadline-monotonic()))
        return self._finish(client,listeners,subscriptions,state,names,LifecycleFailureStage.NONE if state["market"] else LifecycleFailureStage.NO_MARKET_EVENT,True)
    @staticmethod
    def _event_name(value: str|Mapping[str,Any]) -> str|None:
        try: parsed=json.loads(value) if isinstance(value,str) else value
        except (TypeError,ValueError): return None
        name=parsed.get("event") if isinstance(parsed,Mapping) else None
        return name if isinstance(name,str) else None
    def _finish(self, client: object, listeners: tuple[tuple[str,object],...], subscriptions: tuple[dict[str,object],...], state: dict[str,bool], names: list[str], stage: LifecycleFailureStage, created: bool) -> LifecycleStatus:
        if state["subscribe"]:
            for params in subscriptions:
                try: client.unsubscribe(params)
                except Exception: state["unsub"]=False; stage=LifecycleFailureStage.UNSUBSCRIBE_FAILED if stage is LifecycleFailureStage.NONE else stage
        try: client.disconnect()
        except Exception: state["disconnect"]=False; stage=LifecycleFailureStage.DISCONNECT_FAILED if stage is LifecycleFailureStage.NONE else stage
        self._remove(client,listeners)
        return LifecycleStatus(created,True,True,state["connected"],"AUTHENTICATED" if state["authenticated"] else ("UNAUTHENTICATED" if state["unauthenticated"] else "UNKNOWN"),state["subscribe"],state["ack"],state["heartbeat"],state["market"],state["tx_count"],state["tmf_count"],state["unsub"],state["disconnect"],stage,tuple(names),tuple(subscriptions))
    @staticmethod
    def _remove(client: object, listeners: tuple[tuple[str,object],...]) -> None:
        for event, listener in listeners:
            try: client.off(event,listener)
            except Exception: pass
    @staticmethod
    def _empty(stage: LifecycleFailureStage) -> LifecycleStatus:
        return LifecycleStatus(False,False,False,False,"UNKNOWN",False,False,False,False,0,0,False,False,stage,(),())
