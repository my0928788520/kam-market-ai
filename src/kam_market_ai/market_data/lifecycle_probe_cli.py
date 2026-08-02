from __future__ import annotations
import argparse, json
from ..authorization.bootstrap import AuthorizationBootstrap, AuthorizationFailure, AuthorizationSettings
from .lifecycle_probe import WebSocketLifecycleProbe
from .realtime_probe import ActiveContractProbe

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--duration-seconds",type=float,default=30.0); args=parser.parse_args()
    try: clients=AuthorizationBootstrap().run(AuthorizationSettings.from_local_env(),dry_run=False).clients
    except AuthorizationFailure as error: print(json.dumps({"failure_stage":error.stage.value})); return 1
    probe=WebSocketLifecycleProbe()
    stock=probe.run(clients.stock_websocket,(probe.stock_subscription(),),duration_seconds=args.duration_seconds)
    output={"stock":stock.safe_payload()}
    if stock.failure_stage.value!="NONE":
        output["futopt_not_run_reason"]="stock prerequisite failed"; print(json.dumps(output,ensure_ascii=False)); return 1
    try: contracts=ActiveContractProbe(clients).resolve()
    except Exception as error: output["futopt_failure_stage"]="CLIENT_INIT_FAILED"; output["futopt_error_type"]=type(error).__name__; print(json.dumps(output,ensure_ascii=False)); return 1
    futopt=probe.run(clients.futopt_websocket,(probe.futures_subscription(contracts.tx_symbol),probe.futures_subscription(contracts.tmf_symbol)),duration_seconds=args.duration_seconds)
    output["active_tx_symbol"]=contracts.tx_symbol; output["active_tmf_symbol"]=contracts.tmf_symbol; output["futopt"]=futopt.safe_payload(); print(json.dumps(output,ensure_ascii=False)); return 0 if futopt.failure_stage.value=="NONE" else 1
if __name__=="__main__": raise SystemExit(main())
