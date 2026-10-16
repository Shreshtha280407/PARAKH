#!/usr/bin/env python3
"""Local P8 physical sync test: transparent bounded upload rate, no logging/body storage.

Only localhost:18009 -> localhost:18008. Gives the host a deterministic opportunity
to stop the QA process mid-upload; actual P6 bytes, signatures and API remain intact.
Not an inference/upload performance benchmark. Stop with Ctrl-C after testing.
"""
import argparse
import asyncio
import contextlib


async def forward(reader, writer, rate=None):
    while data := await reader.read(65536):
        writer.write(data)
        await writer.drain()
        if rate:
            await asyncio.sleep(len(data) / rate)


async def connection(reader, writer, rate):
    upstream = None
    tasks = []
    try:
        source, upstream = await asyncio.open_connection("127.0.0.1", 18008)
        tasks = [asyncio.create_task(forward(reader, upstream, rate)),
                 asyncio.create_task(forward(source, writer))]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (OSError, asyncio.CancelledError):
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for stream in (writer, upstream):
            if stream:
                stream.close()
                with contextlib.suppress(OSError):
                    await stream.wait_closed()


async def serve(rate):
    server = await asyncio.start_server(lambda r, w: connection(r, w, rate), "127.0.0.1", 18009)
    print(f"P8 loopback test proxy ready on 18009 -> 18008; upload cap {rate} bytes/s", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload-bytes-per-second", type=int, default=1048576)
    args = parser.parse_args()
    assert 262144 <= args.upload_bytes_per_second <= 10485760
    try:
        asyncio.run(serve(args.upload_bytes_per_second))
    except KeyboardInterrupt:
        pass
