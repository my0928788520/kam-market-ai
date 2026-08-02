"""Small standard-library WSGI app for a supplied Replay presenter only."""
from pathlib import Path
from .presenter import ReplayPresenterView
from .wsgi_adapter import ReplayWSGIAdapterConfig,build_replay_wsgi_context
from .ui_contract import render_replay_ui
class ReplayApp:
 def __init__(self,presenter:ReplayPresenterView,config:ReplayWSGIAdapterConfig|None=None): self.presenter=presenter; self.config=config or ReplayWSGIAdapterConfig()
 def __call__(self,environ,start_response):
  path=str(environ.get("PATH_INFO","/")); method=str(environ.get("REQUEST_METHOD","GET")).upper()
  if method!="GET": start_response("405 Method Not Allowed",[("Content-Type","text/plain; charset=utf-8")]); return [b"Method Not Allowed"]
  if path=="/replay/static/replay_dashboard.css":
   body=(Path(__file__).with_name("static")/"replay_dashboard.css").read_bytes(); start_response("200 OK",[("Content-Type","text/css; charset=utf-8"),("Cache-Control","no-store")]); return [body]
  if path!="/replay": start_response("404 Not Found",[("Content-Type","text/plain; charset=utf-8")]); return [b"Not Found"]
  try:
   context=build_replay_wsgi_context(self.presenter,self.config); body=render_replay_ui(context).encode(); start_response("200 OK",list(context.response_headers)); return [body]
  except Exception:
   start_response("500 Internal Server Error",[("Content-Type","text/plain; charset=utf-8"),("Cache-Control","no-store")]); return [b"Replay rendering unavailable"]
