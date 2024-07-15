import websockets
import asyncio

async def main(filename="./chats/destiny.txt", ws_url='wss://chat.destiny.gg/ws'):
    while True:
        try:
            await _main(filename, ws_url)
        except Exception as e:
            print(f"Error: {e}")

async def _main(filename, ws_url):
    with open(filename, "a") as file:
        await connectToWS(file, ws_url)

async def connectToWS(file, ws_url):
    async with websockets.connect(ws_url, ping_interval=None) as websocket:
        #await websocket.send('Hello, World!')
        while True:
            response = await websocket.recv()
            #print(response)
            file.write(response)
            file.write("\n")
            #file.flush()

if __name__ == '__main__':
    asyncio.run(main())
    