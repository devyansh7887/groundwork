import asyncio
from main import _run_and_cache

async def run():
    print('Starting analysis for Kludex/starlette...')
    res = await _run_and_cache('https://github.com/Kludex/starlette', None, 'technical', force_refresh=True)
    print(f'Finished successfully! SHA: {res.get("sha")}')

asyncio.run(run())
