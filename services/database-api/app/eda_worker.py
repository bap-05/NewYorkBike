"""Supervise an isolated EDA process; HTTP requests never generate figures."""
import asyncio
import logging
import os
from pathlib import Path
import subprocess
import sys

logger = logging.getLogger('citibike.eda')
ROOT = Path(__file__).resolve().parents[3]


async def refresh_loop(root, interval=900):
    while True:
        process = None
        try:
            kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
            process = await asyncio.create_subprocess_exec(sys.executable, '-m', 'eda.main',
                '--auto-once', '--output', str(root), '--max-rows', '200000',
                cwd=str(ROOT), **kwargs)
            code = await process.wait()
            if code:
                logger.error('Automatic EDA failed; previous completed report remains available.')
        except asyncio.CancelledError:
            if process is not None and process.returncode is None:
                process.terminate()
                await process.wait()
            raise
        except Exception as exc:
            logger.error('Automatic EDA could not start (%s).', type(exc).__name__)
        await asyncio.sleep(interval)
