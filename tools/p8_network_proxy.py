#!/usr/bin/env python3
"""Local P8 physical sync test: transparent bounded upload rate, no logging/body storage.

Only localhost:18009 -> localhost:18008. Gives the host a deterministic opportunity
to stop the QA process mid-upload; actual P6 bytes, signatures and API remain intact.
Not an inference/upload performance benchmark. Stop with Ctrl-C after testing.

Units (P10 fix): the master plan's degraded-network target is phrased in
kbps (kilobits/second, decimal telecom convention -- 1 kbps = 1000 bits/s),
but this tool's rate knob is bytes/second. 256 kbps = 256,000 bits/s =
32,000 bytes/s -- NOT 256 KiB/s (262,144 bytes/s, ~8.2x faster), which an
earlier P10 pass mistakenly used by reading "256" and "kbps" as if that
value were already in bytes. Use --upload-kbps to specify the rate the way
the master plan actually states it and avoid repeating that mistake; the
older --upload-bytes-per-second flag still works unchanged for scripts
that already use it.
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
    rate_group = parser.add_mutually_exclusive_group()
    rate_group.add_argument("--upload-bytes-per-second", type=int, default=None)
    rate_group.add_argument(
        "--upload-kbps", type=float, default=None,
        help="decimal kilobits/second (1 kbps = 1000 bits/s) -- the unit the master plan's degraded-"
             "network target actually uses, e.g. --upload-kbps 256 for the original 256 kbps target",
    )
    args = parser.parse_args()
    if args.upload_kbps is not None:
        rate = round(args.upload_kbps * 1000 / 8)
    elif args.upload_bytes_per_second is not None:
        rate = args.upload_bytes_per_second
    else:
        rate = 1048576  # 1 MiB/s, the pre-existing default -- unthrottled-ish, for interruption testing
    # Floor covers down to the master plan's 256 kbps (32,000 bytes/s) with
    # headroom for lower simulated rates; ceiling matches the pre-existing bound.
    assert 8192 <= rate <= 10485760, f"rate {rate} bytes/s is out of the supported 8192-10485760 range"
    try:
        asyncio.run(serve(rate))
    except KeyboardInterrupt:
        pass
