import json
import websocket


def on_open(ws):
    print("=" * 60)
    print("CONNECTED")
    print("=" * 60)


def on_message(ws, message):
    data = json.loads(message)

    print(
        f"""
SYMBOL : {data['symbol']}
LTP    : {data['ltp']}
OPEN   : {data['open']}
HIGH   : {data['high']}
LOW    : {data['low']}
CLOSE  : {data['close']}
VOLUME : {data['volume']}
-------------------------------------------------------
"""
    )


def on_error(ws, error):
    print(error)


def on_close(ws, code, msg):
    print("Disconnected")


ws = websocket.WebSocketApp(
    "ws://127.0.0.1:8000/ws/market/",
    on_open=on_open,
    on_message=on_message,
    on_error=on_error,
    on_close=on_close,
)

ws.run_forever()
