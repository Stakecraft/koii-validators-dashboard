from os import getenv
from dotenv import load_dotenv
import gc
from typing import Dict, Any
from time import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv()

class Config:
    # Cache storage
    _cache: Dict[str, Any] = {}
    _cache_timestamps: Dict[str, float] = {}
    _last_gc_run: float = time()
    _gc_interval: int = 3600  # Run garbage collection every hour

    # API Endpoints
    API_ENDPOINT = getenv('API_ENDPOINT')
    KOII_RPC_URL = getenv('KOII_RPC_URL')
    CRYPTORANK_API_URL = getenv('CRYPTORANK_API_URL')
    CRYPTORANK_API_KEY = getenv('CRYPTORANK_API_KEY')
    VALIDATORS_API_URL = getenv('VALIDATORS_API_URL')

    # Cache TTLs (in seconds)
    PRICE_CACHE_TTL = int(getenv('PRICE_CACHE_TTL', '600'))

    # External URLs
    KOII_LOGO_URL = getenv('KOII_LOGO_URL')
    STAKECRAFT_URL = getenv('STAKECRAFT_URL')
    STAKECRAFT_TWITTER_URL = getenv('STAKECRAFT_TWITTER_URL')
    STAKECRAFT_TELEGRAM_URL = getenv('STAKECRAFT_TELEGRAM_URL')
    STAKECRAFT_DISCORD_URL = getenv('STAKECRAFT_DISCORD_URL')
    STAKECRAFT_EMAIL = getenv('STAKECRAFT_EMAIL')

    # Map Tiles
    MAP_LIGHT_TILES_URL = getenv('MAP_LIGHT_TILES_URL')
    MAP_DARK_TILES_URL = getenv('MAP_DARK_TILES_URL')

    # Update Interval (in milliseconds)
    REFRESH_INTERVAL = getenv('REFRESH_INTERVAL')

    STADIA_MAPS_API_KEY = getenv('STADIA_MAPS_API_KEY')

    @classmethod
    def run_garbage_collection(cls) -> None:
        """Run garbage collection if enough time has passed since last run"""
        current_time = time()
        
        # Check if it's time to run GC
        if current_time - cls._last_gc_run < cls._gc_interval:
            return

        try:
            # Clean up expired cache entries
            expired_keys = [
                key for key, timestamp in cls._cache_timestamps.items()
                if current_time - timestamp > cls.PRICE_CACHE_TTL
            ]
            
            for key in expired_keys:
                cls._cache.pop(key, None)
                cls._cache_timestamps.pop(key, None)

            # Force Python's garbage collector
            collected = gc.collect()
            
            logger.info(f"Garbage collection completed: {collected} objects collected")
            logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
            
            # Update last GC run timestamp
            cls._last_gc_run = current_time
            
        except Exception as e:
            logger.error(f"Error during garbage collection: {e}")

    @classmethod
    def cache_set(cls, key: str, value: Any) -> None:
        """Set a value in the cache with current timestamp"""
        cls._cache[key] = value
        cls._cache_timestamps[key] = time()
        
        # Run garbage collection if needed
        cls.run_garbage_collection()

    @classmethod
    def cache_get(cls, key: str) -> Any:
        """Get a value from the cache if not expired"""
        if key not in cls._cache:
            return None
            
        timestamp = cls._cache_timestamps.get(key)
        if timestamp is None:
            return None
            
        # Check if cache entry has expired
        if time() - timestamp > cls.PRICE_CACHE_TTL:
            cls._cache.pop(key, None)
            cls._cache_timestamps.pop(key, None)
            return None
            
        return cls._cache.get(key)

    @classmethod
    def to_dict(cls):
        """Convert config to dictionary for template rendering"""
        # Run garbage collection before returning config
        cls.run_garbage_collection()
        
        return {
            'API_ENDPOINT': cls.API_ENDPOINT,
            'KOII_LOGO_URL': cls.KOII_LOGO_URL,
            'STAKECRAFT_URL': cls.STAKECRAFT_URL,
            'STAKECRAFT_TWITTER_URL': cls.STAKECRAFT_TWITTER_URL,
            'STAKECRAFT_TELEGRAM_URL': cls.STAKECRAFT_TELEGRAM_URL,
            'STAKECRAFT_DISCORD_URL': cls.STAKECRAFT_DISCORD_URL,
            'STAKECRAFT_EMAIL': cls.STAKECRAFT_EMAIL,
            'MAP_LIGHT_TILES_URL': cls.MAP_LIGHT_TILES_URL,
            'MAP_DARK_TILES_URL': cls.MAP_DARK_TILES_URL,
            'REFRESH_INTERVAL': cls.REFRESH_INTERVAL,
            'VALIDATORS_API_URL': cls.VALIDATORS_API_URL,
            'CRYPTORANK_API_KEY': cls.CRYPTORANK_API_KEY,
        }