import json, csv, aiofiles, os, pandas as pd
from pathlib import Path
from loguru import logger
import aiohttp

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

async def save(kind: str, payload: list | dict, name: str) -> Path:
    file_stem = DATA_DIR / name
    
    # CSV for tabular data
    if kind == "csv" or (isinstance(payload, list) and payload and isinstance(payload[0], dict)):
        out = file_stem.with_suffix(".csv")
        df = pd.DataFrame(payload)
        df.to_csv(out, index=False)
        
    # JSON for nested data
    elif kind == "json":
        out = file_stem.with_suffix(".json")
        async with aiofiles.open(out, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload, indent=2, ensure_ascii=False))
            
    # Image downloads
    elif kind in ["png", "jpg", "jpeg", "webp"]:
        out = file_stem.with_suffix(f".{kind}")
        # payload is list of URLs
        async with aiohttp.ClientSession() as session:
            for i, url in enumerate(payload[:10]):  # limit to 10
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            img_path = out.parent / f"{name}_{i}.{kind}"
                            async with aiofiles.open(img_path, "wb") as f:
                                await f.write(data)
                            logger.success(f"Downloaded {img_path.name}")
                except Exception as e:
                    logger.warning(f"Failed to download {url}: {e}")
        return out.parent  # return dir, not single file
        
    else:
        out = file_stem.with_suffix(".txt")
        async with aiofiles.open(out, "w", encoding="utf-8") as f:
            await f.write(str(payload))
            
    logger.success(f"Saved {out.name}")
    return out