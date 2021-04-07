from aiohttp import ClientSession

_session = None


async def get_session() -> ClientSession:
    """This is the way to retrieve a ClientSession to make HTTP requests.

    ClientSession needs to be created inside an async function, so by
    calling this, you ensure it exists, or create it if it doesn't.

    Since there are some connection pools, we don't want to be creating
    these all the time.  Better to just reuse one."""
    global _session
    if not _session:
        _session = ClientSession()
    return _session
