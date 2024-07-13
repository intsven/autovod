import websockets
import asyncio
#import requests
from curl_cffi import requests
import sys


async def main(streamer):
    filename = f"./chats/kick/{streamer}.txt"
    # Get the chat id
    url = f"https://kick.com/api/v1/channels/{streamer}"
    res = requests.get(url, impersonate="chrome110")

    #print(res.text)
    chat_id = res.json()["chatroom"]["id"]
    print(f"Chat ID: {chat_id} for {streamer}")
    while True:
        try:
            await _main(filename, chat_id)
        except Exception as e:
            print(f"Error: {e}")

async def _main(filename, chat_id):
    #file = open(filename, "a")
    with open(filename, "a") as file:
        await connectToWS(file, chat_id)

async def connectToWS(file, chat_id):
    ws_url = "wss://ws-us2.pusher.com/app/eb1d5f283081a78b932c?protocol=7&client=js&version=7.6.0&flash=false"
    subMsg = '{"event":"pusher:subscribe","data":{"auth":"","channel":"chatrooms.' + str(chat_id) + '.v2"}}'
    async with websockets.connect(ws_url, ping_interval=None) as websocket:
        await websocket.send(subMsg)
        while True:
            response = await websocket.recv()
            #print(response)
            file.write(response)
            file.write("\n")
            #file.flush()

if __name__ == '__main__':
    streamer="gogirl"
    if len(sys.argv) > 1:
        streamer = sys.argv[1]
    asyncio.run(main(streamer))
    