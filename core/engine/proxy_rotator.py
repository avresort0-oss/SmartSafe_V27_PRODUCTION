"""
Smart Anti-Ban Engine - Proxy Rotator
Per-account SOCKS5/HTTP proxy rotation with health checks
"""

import json
import random
import time
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
try:
    import PySocks
    PYSOCKS_AVAILABLE = True
except ImportError:
    PYSOCKS_AVAILABLE = False

from core.config import SETTINGS

logger = logging.getLogger(__name__)

@dataclass
class Proxy:
    type: str  # 'http', 'socks5'
    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    
    @property
    def url(self) -> str:
        """Proxy URL for requests"""
        if self.type == 'http':
            auth = f"{self.username}:{self.password}@" if self.username else ""
            return f"http://{auth}{self.host}:{self.port}"
        elif self.type == 'socks5':
            auth = f"{self.username}:{self.password}@" if self.username else ""
            return f"socks5://{auth}{self.host}:{self.port}"
        raise ValueError(f"Unknown proxy type: {self.type}")

class ProxyRotator:
    """
    Per-account proxy rotator with health checking and rotation.
    
    Features:
    - Loads proxies from proxies.json or account-specific list
    - Automatic health checks (connectivity test)
    - Intelligent rotation (avoid dead proxies)
    - SOCKS5/HTTP support
    """
    
    def __init__(self, proxies_file: str = None):
        self.proxies_file = proxies_file or SETTINGS.proxies_file
        self.proxies_path = Path(self.proxies_file)
        self.global_proxies: List[Proxy] = []
        self.account_proxies: Dict[str, List[Proxy]] = {}
        self.proxy_health: Dict[str, Dict] = {}  # proxy_url -> {healthy:bool, last_test:float}
        self.rotation_index: Dict[str, int] = {}  # account -> index
        self._load_proxies()
    
    def _load_proxies(self):
        """Load global proxies from file"""
        if not self.proxies_path.exists():
            logger.warning(f"Proxies file not found: {self.proxies_path}")
            return
        
        try:
            with open(self.proxies_path, 'r') as f:
                data = json.load(f)
            
            for proxy_data in data:
                try:
                    proxy = Proxy(
                        type=proxy_data.get('type', 'http'),
                        host=proxy_data['host'],
                        port=int(proxy_data['port']),
                        username=proxy_data.get('username'),
                        password=proxy_data.get('password')
                    )
                    self.global_proxies.append(proxy)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Invalid proxy data: {proxy_data}, error: {e}")
            
            logger.info(f"Loaded {len(self.global_proxies)} global proxies")
        except Exception as e:
            logger.error(f"Failed to load proxies: {e}")
    
    def set_account_proxies(self, account: str, proxies: List[Dict]):
        """Set account-specific proxy list"""
        proxy_list = []
        for proxy_data in proxies:
            try:
                proxy = Proxy(
                    type=proxy_data.get('type', 'http'),
                    host=proxy_data['host'],
                    port=int(proxy_data['port']),
                    username=proxy_data.get('username'),
                    password=proxy_data.get('password')
                )
                proxy_list.append(proxy)
            except Exception as e:
                logger.warning(f"Invalid account proxy for {account}: {e}")
        
        self.account_proxies[account] = proxy_list
        self.rotation_index[account] = 0
        logger.info(f"Set {len(proxy_list)} proxies for account {account}")
    
    def get_next_proxy(self, account: str = None) -> Optional[Tuple[Proxy, Dict]]:
        """
        Get next healthy proxy for account.
        
        Returns: (proxy, health_info) or None if no healthy proxies
        """
        if not SETTINGS.enable_proxy_rotation:
            return None
        
        # Use account-specific first
        proxies = self.account_proxies.get(account, self.global_proxies)
        if not proxies:
            return None
        
        account_key = account or 'global'
        if account_key not in self.rotation_index:
            self.rotation_index[account_key] = 0
        
        # Find next healthy proxy (rotate through list)
        start_index = self.rotation_index[account_key]
        for i in range(len(proxies)):
            idx = (start_index + i) % len(proxies)
            proxy = proxies[idx]
            proxy_url = proxy.url
            
            # Check health if stale
            health = self._get_proxy_health(proxy_url)
            if health['healthy']:
                # Update rotation index
                self.rotation_index[account_key] = (idx + 1) % len(proxies)
                return proxy, health
        
        # No healthy proxy found, test and rotate
        for i in range(len(proxies)):
            idx = (start_index + i) % len(proxies)
            proxy = proxies[idx]
            proxy_url = proxy.url
            
            # Test proxy health
            health = self._test_proxy_health(proxy)
            if health['healthy']:
                self.proxy_health[proxy_url] = health
                self.rotation_index[account_key] = (idx + 1) % len(proxies)
                return proxy, health
        
        logger.warning(f"No healthy proxies for {account}")
        return None
    
    def _get_proxy_health(self, proxy_url: str) -> Dict:
        """Get cached proxy health (with TTL)"""
        now = time.time()
        health = self.proxy_health.get(proxy_url, {})
        
        # TTL: retest every 5 minutes
        if now - health.get('last_test', 0) > 300:
            proxy = self._parse_proxy_url(proxy_url)  # Need reverse parse
            health = self._test_proxy_health(proxy)
            self.proxy_health[proxy_url] = health
        
        return health
    
    def _test_proxy_health(self, proxy: Proxy) -> Dict:
        """Test proxy connectivity"""
        try:
            session = requests.Session()
            
            # SOCKS support
            if PYSOCKS_AVAILABLE and proxy.type == 'socks5':
                session.proxies = {'http': proxy.url, 'https': proxy.url}
            else:
                session.proxies = {'http': proxy.url, 'https': proxy.url}
            
            # Quick test: Google DNS (fast, reliable)
            resp = session.get('http://www.google.com', timeout=5)
            healthy = resp.status_code == 200
            
            return {
                'healthy': healthy,
                'last_test': time.time(),
                'response_time': resp.elapsed.total_seconds() if healthy else None
            }
        except Exception as e:
            logger.debug(f"Proxy health test failed {proxy.url}: {e}")
            return {
                'healthy': False,
                'last_test': time.time(),
                'error': str(e)
            }
    
    def mark_proxy_failed(self, proxy_url: str):
        """Mark proxy as failed (immediate health update)"""
        self.proxy_health[proxy_url] = {
            'healthy': False,
            'last_test': time.time(),
            'error': 'recent_failure'
        }
    
    def get_stats(self, account: str = None) -> Dict:
        """Get rotation statistics"""
        proxies = self.account_proxies.get(account, self.global_proxies)
        healthy_count = sum(1 for p in proxies if self._get_proxy_health(p.url)['healthy'])
        
        return {
            'total_proxies': len(proxies),
            'healthy_proxies': healthy_count,
            'rotation_enabled': SETTINGS.enable_proxy_rotation,
            'rotation_interval': SETTINGS.proxy_rotation_interval
        }

# Global singleton
_proxy_rotator: Optional[ProxyRotator] = None

def get_proxy_rotator() -> ProxyRotator:
    global _proxy_rotator
    if _proxy_rotator is None:
        _proxy_rotator = ProxyRotator()
    return _proxy_rotator

