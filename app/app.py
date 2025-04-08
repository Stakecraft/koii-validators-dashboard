from flask import Flask, render_template, jsonify, request
import requests
import json
from datetime import datetime
import threading
import psycopg2
from psycopg2.extras import DictCursor
from dotenv import load_dotenv
import os
from functools import lru_cache
import time
import logging
from typing import Dict, List, Optional, Any
import subprocess
from .config import Config

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Cache configuration
CACHE_TTL = 30  # seconds
last_cache_time = 0
cached_data = None

# Cache for IP geolocation data
ip_cache = {}

# Cache for KOII price data
price_cache = None
last_price_cache_time = 0

# Add this at the top with other cache variables
node_info_cache = {}
last_node_info_cache_time = 0
NODE_INFO_CACHE_TTL = 300  # 5 minutes

# Database configuration
DB_CONFIG = {
    'dbname': os.getenv('DB_NAME', 'koii_validators'),
    'user': os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', 'postgres'),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': os.getenv('DB_PORT', '5432')
}

def init_db():
    """Initialize database tables if they don't exist"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # Create tables
            cur.execute("""
                CREATE TABLE IF NOT EXISTS latest_validator_data (
                    id SERIAL PRIMARY KEY,
                    data JSONB NOT NULL,
                    timestamp TIMESTAMPTZ DEFAULT NOW()
                )
            """)
            conn.commit()
            logger.info("Database tables initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
    finally:
        if conn:
            conn.close()

def store_latest_data(data: Dict[str, Any]):
    """Store the latest validator data in the database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor() as cur:
            # Store new data
            cur.execute("""
                INSERT INTO latest_validator_data (data)
                VALUES (%s)
            """, (json.dumps(data),))
            
            # Keep only the latest record
            cur.execute("""
                DELETE FROM latest_validator_data
                WHERE id NOT IN (
                    SELECT id FROM latest_validator_data
                    ORDER BY timestamp DESC
                    LIMIT 1
                )
            """)
            conn.commit()
            logger.info("Latest validator data stored in database")
    except Exception as e:
        logger.error(f"Error storing data in database: {e}")
    finally:
        if conn:
            conn.close()

def get_latest_data() -> Optional[Dict[str, Any]]:
    """Get the latest validator data from the database"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        with conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
                SELECT data, timestamp
                FROM latest_validator_data
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            result = cur.fetchone()
            if result:
                data, timestamp = result
                age_seconds = (datetime.now() - timestamp.replace(tzinfo=None)).total_seconds()
                logger.info(f"Retrieved cached data from database (age: {age_seconds:.1f} seconds)")
                return data
            return None
    except Exception as e:
        logger.error(f"Error retrieving data from database: {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_cached_data() -> Optional[Dict[str, Any]]:
    global last_cache_time, cached_data
    current_time = time.time()
    if cached_data and (current_time - last_cache_time) < CACHE_TTL:
        return cached_data
    return None

def set_cached_data(data: Dict[str, Any]) -> None:
    global last_cache_time, cached_data
    cached_data = data
    last_cache_time = time.time()

@lru_cache(maxsize=1)
def get_block_production() -> Dict[str, List[int]]:
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBlockProduction",
            "params": [{
                "startSlot": 0,
                "limit": 150
            }]
        }
        logger.info(f"Making RPC request to: {Config.KOII_RPC_URL}")
        
        # Add proper headers for JSON-RPC request
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        response = requests.post(Config.KOII_RPC_URL, json=payload, headers=headers, timeout=10)
        logger.info(f"Response status code: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        
        # Check content type
        content_type = response.headers.get('content-type', '')
        logger.info(f"Response content type: {content_type}")
        
        if response.status_code != 200:
            logger.error(f"RPC endpoint returned status code {response.status_code}")
            logger.error(f"Response text: {response.text[:200]}...")
            return {}

        if 'application/json' not in content_type.lower():
            logger.error(f"Unexpected content type from RPC endpoint: {content_type}")
            logger.error(f"Response text: {response.text[:200]}...")  # Log first 200 chars
            return {}

        try:
            data = response.json()
        except ValueError as e:
            logger.error(f"Failed to parse JSON from RPC endpoint: {str(e)}")
            logger.error(f"Response text: {response.text[:200]}...")  # Log first 200 chars
            return {}

        if "error" in data:
            logger.error(f"Error in block production: {data['error']}")
            return {}
        return data["result"]["value"]["byIdentity"]
    except Exception as e:
        logger.error(f"Error getting block production: {e}", exc_info=True)
        return {}

def get_cluster_nodes() -> Dict[str, str]:
    """Get all node IPs from the cluster."""
    global node_info_cache, last_node_info_cache_time
    
    current_time = time.time()
    if node_info_cache and (current_time - last_node_info_cache_time) < NODE_INFO_CACHE_TTL:
        return node_info_cache
        
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getClusterNodes",
            "params": []
        }
        response = requests.post(Config.KOII_RPC_URL, json=payload)

        # Check content type
        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type.lower():
            logger.error(f"Unexpected content type from RPC endpoint: {content_type}")
            logger.error(f"Response text: {response.text[:200]}...")  # Log first 200 chars
            return {}

        try:
            data = response.json()
        except ValueError as e:
            logger.error(f"Failed to parse JSON from RPC endpoint: {str(e)}")
            logger.error(f"Response text: {response.text[:200]}...")  # Log first 200 chars
            return {}
            
        if "error" in data:
            logger.error(f"RPC error in getClusterNodes: {data['error']}")
            return {}
            
        if "result" not in data:
            logger.error("Unexpected response structure from getClusterNodes")
            return {}
            
        # Build a map of pubkey to IP
        node_map = {}
        for node in data["result"]:
            pubkey = node.get("pubkey")
            gossip = node.get("gossip")
            if pubkey and gossip:
                # Extract IP from gossip address (format: IP:PORT)
                ip = gossip.split(":")[0]
                if ip and ip != "0.0.0.0":
                    node_map[pubkey] = ip
        
        # Update cache
        node_info_cache = node_map
        last_node_info_cache_time = current_time
        
        return node_map
        
    except Exception as e:
        logger.error(f"Error getting cluster nodes: {e}")
        return {}

def get_validator_ip(identity_pubkey: str) -> Optional[str]:
    """Get the IP address of a validator."""
    try:
        # Get node information from cache or fresh
        node_map = get_cluster_nodes()
        
        # Look up the IP for this validator
        if identity_pubkey in node_map:
            return node_map[identity_pubkey]
            
        logger.warning(f"No IP found for validator {identity_pubkey}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting validator IP for {identity_pubkey}: {e}")
        return None

def get_location_from_ip(ip: str) -> Optional[Dict[str, Any]]:
    """Get location data for an IP address using IP-API."""
    if ip in ip_cache:
        return ip_cache[ip]
        
    try:
        response = requests.get(f'http://ip-api.com/json/{ip}')
        if response.status_code == 200:
            data = response.json()
            if data['status'] == 'success':
                location = {
                    'latitude': data['lat'],
                    'longitude': data['lon'],
                    'city': data['city'],
                    'country': data['country']
                }
                ip_cache[ip] = location
                return location
        return None
    except Exception as e:
        logger.error(f"Error getting location for IP {ip}: {e}")
        return None

def get_validator_rewards(vote_accounts: List[str], epoch: Optional[int] = None) -> Dict[str, float]:
    try:
        # Get current epoch if not specified
        if epoch is None:
            epoch_payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "getEpochInfo",
                "params": []
            }
            epoch_response = requests.post(Config.KOII_RPC_URL, json=epoch_payload)
            if epoch_response.status_code == 200:
                epoch_data = epoch_response.json()
                if "result" in epoch_data:
                    current_epoch = epoch_data["result"].get("epoch")
                    # Use previous epoch
                    epoch = current_epoch - 1
                else:
                    logger.error("Failed to get current epoch")
                    return {}
            else:
                logger.error(f"Failed to get epoch info: HTTP status code {epoch_response.status_code}")
                return {}

        # Get finalized slot for the epoch
        slot_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getEpochSchedule",
            "params": []
        }
        slot_response = requests.post(Config.KOII_RPC_URL, json=slot_payload)
        if slot_response.status_code == 200:
            slot_data = slot_response.json()
            if "result" in slot_data:
                slots_per_epoch = slot_data["result"].get("slotsPerEpoch", 432000)
                # Use a slot from the middle of the epoch to ensure it's finalized
                target_slot = (epoch * slots_per_epoch) + (slots_per_epoch // 2)
            else:
                logger.error("Failed to get epoch schedule")
                return {}
        else:
            logger.error(f"Failed to get epoch schedule: HTTP status code {slot_response.status_code}")
            return {}

        # Create params array with vote account addresses
        params = [vote_accounts]  # Pass as array of arrays
        params.append({
            "epoch": epoch,
            "commitment": "finalized",
            "minContextSlot": target_slot
        })

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getInflationReward",
            "params": params
        }
        
        response = requests.post(Config.KOII_RPC_URL, json=payload)
        if response.status_code != 200:
            logger.error(f"Failed to get inflation rewards: HTTP status code {response.status_code}")
            return {}

        data = response.json()
        if "error" in data:
            logger.error(f"Error getting inflation rewards: {data['error']}")
            return {}

        result = data.get("result", [])
        if not result or not isinstance(result, list):
            logger.error("No result data in inflation rewards response")
            return {}

        # Process all rewards
        rewards = {}
        for i, reward_data in enumerate(result):
            if i >= len(vote_accounts):
                break
            vote_account = vote_accounts[i]
            if reward_data:
                reward = reward_data.get("amount", 0) / 1e9
                rewards[vote_account] = reward
            else:
                rewards[vote_account] = 0

        return rewards
    except Exception as e:
        logger.error(f"Error getting inflation rewards: {e}", exc_info=True)
        return {}

def calculate_validator_metrics(validator: Dict[str, Any], block_production: Dict[str, List[int]], total_stake: int, inflation_rate: float, rewards: Dict[str, float], all_validators: List[Dict[str, Any]], network_apr: float) -> Dict[str, Any]:
    try:
        vote_pubkey = str(validator.get("votePubkey", ""))
        identity_pubkey = str(validator.get("nodePubkey", vote_pubkey))
        stake = int(validator.get("activatedStake", 0))
        commission = int(validator.get("commission", 0)) / 100  # Convert percentage to decimal
        
        # Skip rate calculation
        skip_rate = 0
        if identity_pubkey in block_production:
            slots = block_production[identity_pubkey]
            assigned_slots = int(slots[0])
            produced_blocks = int(slots[1])
            missed_slots = assigned_slots - produced_blocks
            skip_rate = (missed_slots / assigned_slots) * 100 if assigned_slots > 0 else 0
        
        # Calculate epoch credits growth
        epoch_credits = validator.get("epochCredits", [])
        credits_growth = 0
        if len(epoch_credits) >= 2:
            latest = epoch_credits[-1]
            previous = epoch_credits[-2]
            credits_growth = latest[2] - previous[2]
        
        # Get rewards from the rewards dictionary
        reward = rewards.get(vote_pubkey, 0)
        
        # Calculate validator APR as Network APR minus commission
        validator_apr = network_apr - (network_apr * commission)
        
        # Log validator APR calculation for debugging
        logger.info(f"Validator {identity_pubkey} APR calculation:")
        logger.info(f"  Network APR: {network_apr:.2f}%")
        logger.info(f"  Commission Rate: {commission:.2%}")
        logger.info(f"  Final Validator APR: {validator_apr:.2f}%")
        logger.info("---")
        
        # Get validator IP and location
        ip_address = get_validator_ip(identity_pubkey)
        location = get_location_from_ip(ip_address) if ip_address else None
        
        return {
            'identityPubkey': identity_pubkey,
            'voteAccountPubkey': vote_pubkey,
            'commission': int(validator.get("commission", 0)),
            'lastVote': int(validator.get("lastVote", 0)),
            'rootSlot': int(validator.get("rootSlot", 0)),
            'credits': int(validator.get("credits", 0)),
            'epochCredits': epoch_credits,
            'activatedStake': stake,
            'version': str(validator.get("version", "1.16.0")),
            'skipRate': skip_rate,
            'creditsGrowth': credits_growth,
            'location': location,
            'delinquent': False,
            'apr': validator_apr
        }
    except Exception as e:
        logger.error(f"Error calculating metrics for validator {vote_pubkey}: {e}", exc_info=True)
        return None

def get_inflation_rate() -> Optional[float]:
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getInflationRate",
            "params": []
        }
        response = requests.post(Config.KOII_RPC_URL, json=payload)
        if response.status_code != 200:
            logger.error("Failed to get inflation rate: HTTP status code %d", response.status_code)
            return None

        data = response.json()
        if "error" in data:
            logger.error(f"Error getting inflation rate: {data['error']}")
            return None

        result = data.get("result", {})
        if not result:
            logger.error("No result data in inflation rate response")
            return None

        # Log the complete inflation rate structure
        logger.info(f"Complete inflation rate result: {json.dumps(result, indent=2)}")
        
        # Get inflation rate components directly from result
        validator_rate = result.get("validator")
        foundation_rate = result.get("foundation")
        total_rate = result.get("total")
        current_epoch = result.get("epoch")
        
        # Log raw values before conversion
        logger.info("Raw inflation rate values:")
        logger.info(f"  Current epoch: {current_epoch}")
        logger.info(f"  Validator rate (raw): {validator_rate}")
        logger.info(f"  Foundation rate (raw): {foundation_rate}")
        logger.info(f"  Total rate (raw): {total_rate}")
        
        # Convert to float and handle None values
        validator_rate = float(validator_rate) if validator_rate is not None else 0
        foundation_rate = float(foundation_rate) if foundation_rate is not None else 0
        total_rate = float(total_rate) if total_rate is not None else 0
        
        logger.info("Inflation rate components:")
        logger.info(f"  Validator rate: {validator_rate * 100:.2f}%")
        logger.info(f"  Foundation rate: {foundation_rate * 100:.2f}%")
        logger.info(f"  Total rate: {total_rate * 100:.2f}%")
        
        return validator_rate
    except Exception as e:
        logger.error(f"Error getting inflation rate: {e}", exc_info=True)
        return None

def get_total_supply() -> Optional[int]:
    try:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getSupply",
            "params": [{"commitment": "finalized"}]
        }
        response = requests.post(Config.KOII_RPC_URL, json=payload)
        if response.status_code != 200:
            logger.error("Failed to get total supply: HTTP status code %d", response.status_code)
            return None

        data = response.json()
        if "error" in data:
            logger.error(f"Error getting total supply: {data['error']}")
            return None

        result = data.get("result", {})
        if not result:
            logger.error("No result data in supply response")
            return None

        # Get total supply from the nested value object
        value = result.get("value", {})
        if not value:
            logger.error("No value object in supply response")
            return None

        total = value.get("total")
        if total is None:
            logger.error("No total supply value in response")
            return None

        return total
    except Exception as e:
        logger.error(f"Error getting total supply: {e}", exc_info=True)
        return None

def get_validator_info() -> Optional[Dict[str, Any]]:
    try:
        # Check cache first
        cached_data = get_cached_data()
        if cached_data:
            return cached_data

        if not Config.KOII_RPC_URL:
            logger.error("KOII_RPC_URL is not configured")
            return None

        # Get real inflation rate from RPC
        inflation_rate = get_inflation_rate()
        if inflation_rate is None:
            logger.error("Failed to get inflation rate")
            return None

        # Get total supply
        total_supply = get_total_supply()
        if total_supply is None:
            logger.error("Failed to get total supply")
            return None

        # Calculate total rewards using total supply and inflation rate
        total_rewards = (total_supply * inflation_rate) / 1e9  # Convert to KOII
        total_supply_koii = total_supply / 1e9

        logger.info("Network metrics:")
        logger.info(f"Total supply: {total_supply_koii:.2f} KOII")
        logger.info(f"Inflation rate: {inflation_rate * 100:.2f}%")
        logger.info(f"Total rewards: {total_rewards:.2f} KOII")

        # Get validators
        validators_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getVoteAccounts",
            "params": [{
                "commitment": "confirmed"
            }]
        }
        
        # Add proper headers for JSON-RPC request
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        logger.info(f"Making validator RPC request to: {Config.KOII_RPC_URL}")
        
        try:
            response = requests.post(Config.KOII_RPC_URL, json=validators_payload, headers=headers, timeout=10)
            logger.info(f"Response status code: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            
            if response.status_code != 200:
                logger.error(f"RPC endpoint returned status code {response.status_code}")
                logger.error(f"Response text: {response.text[:200]}...")
                return None
            
            # Check content type
            content_type = response.headers.get('content-type', '')
            logger.info(f"Response content type: {content_type}")
            
            if 'application/json' not in content_type.lower():
                logger.error(f"Unexpected content type from RPC endpoint: {content_type}")
                logger.error(f"Response text: {response.text[:200]}...")
                return None

            try:
                validators_response = response.json()
            except ValueError as e:
                logger.error(f"Failed to parse JSON from RPC endpoint: {str(e)}")
                logger.error(f"Response text: {response.text[:200]}...")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to RPC endpoint: {e}")
            return None
        
        if "error" in validators_response:
            logger.error(f"Error getting validators: {validators_response['error']}")
            return None
            
        if "result" not in validators_response:
            logger.error("Unexpected validators response structure:", validators_response)
            return None
            
        current_validators = validators_response["result"].get("current", [])
        delinquent_validators = validators_response["result"].get("delinquent", [])
        
        # Get block production data
        block_production = get_block_production()
        
        # Collect all vote account pubkeys
        all_vote_accounts = []
        for validator in current_validators + delinquent_validators:
            vote_pubkey = str(validator.get("votePubkey", ""))
            if vote_pubkey:
                all_vote_accounts.append(vote_pubkey)
        
        # Get rewards for all validators in a single call
        rewards = get_validator_rewards(all_vote_accounts)
        
        # Process validators
        processed_validators = []
        total_active_stake = 0
        total_current_stake = 0
        total_delinquent_stake = 0
        
        # First pass: calculate total stakes
        for validator in current_validators:
            stake = int(validator.get("activatedStake", 0))
            total_active_stake += stake
            total_current_stake += stake
        
        for validator in delinquent_validators:
            stake = int(validator.get("activatedStake", 0))
            total_delinquent_stake += stake
            total_current_stake += stake
        
        # Calculate Network APR using total rewards and total active stake
        total_stake_in_koii = total_active_stake / 1e9  # Convert lamports to KOII
        network_apr = (total_rewards / total_stake_in_koii) * 100 if total_stake_in_koii > 0 else 0
        
        logger.info("Network APR:")
        logger.info(f"Total active stake: {total_stake_in_koii:.2f} KOII")
        logger.info(f"Network APR: {network_apr:.2f}%")

        # Process validators with the calculated network_apr
        all_validators = current_validators + delinquent_validators
        for validator in current_validators:
            metrics = calculate_validator_metrics(validator, block_production, total_active_stake, inflation_rate, rewards, all_validators, network_apr)
            if metrics:
                metrics['delinquent'] = False
                processed_validators.append(metrics)
        
        for validator in delinquent_validators:
            metrics = calculate_validator_metrics(validator, block_production, total_active_stake, inflation_rate, rewards, all_validators, network_apr)
            if metrics:
                metrics['delinquent'] = True
                processed_validators.append(metrics)
        
        # Calculate statistics
        stats = {
            'totalActiveStake': total_active_stake,
            'totalCurrentStake': total_current_stake,
            'totalDelinquentStake': total_delinquent_stake,
            'validators': processed_validators,
            'averageSkipRate': sum(v['skipRate'] for v in processed_validators) / len(processed_validators) if processed_validators else 0,
            'networkApr': network_apr,
            'inflationRate': inflation_rate * 100,
            'totalValidators': len(processed_validators),
            'activeValidators': len([v for v in processed_validators if not v['delinquent']]),
            'delinquentValidators': len([v for v in processed_validators if v['delinquent']]),
            'stakeByVersion': {}
        }
        
        # Group by version
        for validator in processed_validators:
            version = validator['version']
            if version not in stats['stakeByVersion']:
                stats['stakeByVersion'][version] = {
                    'currentValidators': 0,
                    'delinquentValidators': 0,
                    'currentActiveStake': 0,
                    'delinquentActiveStake': 0,
                    'averageSkipRate': 0,
                    'averageCreditsGrowth': 0,
                    'averageApr': 0,
                    'totalApr': 0,
                    'validatorsWithApr': 0
                }
            
            version_stats = stats['stakeByVersion'][version]
            if validator['delinquent']:
                version_stats['delinquentValidators'] += 1
                version_stats['delinquentActiveStake'] += validator['activatedStake']
            else:
                version_stats['currentValidators'] += 1
                version_stats['currentActiveStake'] += validator['activatedStake']
            
            version_stats['averageSkipRate'] += validator['skipRate']
            version_stats['averageCreditsGrowth'] += validator['creditsGrowth']
            
            # Add APR to version stats
            if validator.get('apr') is not None:
                version_stats['totalApr'] += validator['apr']
                version_stats['validatorsWithApr'] += 1
        
        # Calculate averages for each version
        for version_stats in stats['stakeByVersion'].values():
            total_validators = version_stats['currentValidators'] + version_stats['delinquentValidators']
            if total_validators > 0:
                version_stats['averageSkipRate'] /= total_validators
                version_stats['averageCreditsGrowth'] /= total_validators
                if version_stats['validatorsWithApr'] > 0:
                    version_stats['averageApr'] = version_stats['totalApr'] / version_stats['validatorsWithApr']
        
        # Cache the results
        set_cached_data(stats)
        
        return stats
        
    except Exception as e:
        logger.error(f"Error in get_validator_info: {e}", exc_info=True)
        return None

def get_koii_price() -> Optional[float]:
    try:
        global price_cache, last_price_cache_time
        current_time = time.time()

        # Return cached price if within TTL
        if price_cache is not None and (current_time - last_price_cache_time) < Config.PRICE_CACHE_TTL:
            return price_cache

        # Check if we have an API key
        if not Config.CRYPTORANK_API_KEY:
            logger.warning("No Cryptorank API key configured. Price updates disabled.")
            return price_cache or None

        # Fetch price from Cryptorank API using X-Api-Key header
        headers = {
            'accept': 'application/json',
            'X-Api-Key': Config.CRYPTORANK_API_KEY
        }
        url = Config.CRYPTORANK_API_URL
        
        if not url:
            logger.warning("No Cryptorank API URL configured")
            return price_cache or None

        logger.info(f"Fetching KOII price from Cryptorank API")
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()  # Raise exception for bad status codes
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch price from Cryptorank API: {e}")
            return price_cache or None

        try:
            data = response.json()
            price = data.get('data', {}).get('price')
            if price is not None:
                # Update cache
                price_cache = float(price)
                last_price_cache_time = current_time
                return price_cache
            else:
                logger.warning("Price data not found in Cryptorank API response")
                return price_cache or None
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing Cryptorank API response: {e}")
            return price_cache or None

    except Exception as e:
        logger.error(f"Error fetching KOII price: {e}", exc_info=True)
        return price_cache or None

def get_epoch_info() -> Optional[Dict[str, Any]]:
    try:
        # Get current epoch
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getEpochInfo",
            "params": []
        }
        response = requests.post(Config.KOII_RPC_URL, json=payload)
        if response.status_code != 200:
            logger.error("Failed to get epoch info: HTTP status code %d", response.status_code)
            return None

        data = response.json()
        if "error" in data:
            logger.error(f"Error getting epoch info: {data['error']}")
            return None

        result = data.get("result", {})
        if not result:
            logger.error("No result data in epoch info response")
            return None

        # Log raw epoch data
        logger.info("Raw epoch info: %s", result)

        # Calculate epoch progress
        slot_index = result.get("slotIndex", 0)  # Current slot within the epoch
        slots_in_epoch = result.get("slotsInEpoch", 432000)  # Total slots in epoch
        
        # Log progress calculation values
        logger.info(f"Progress calculation: slot_index={slot_index}, slots_in_epoch={slots_in_epoch}")
        
        # Calculate progress percentage
        progress = (slot_index / slots_in_epoch) * 100 if slots_in_epoch > 0 else 0
        logger.info(f"Calculated progress: {progress}%")

        epoch_info = {
            "currentEpoch": result.get("epoch", 0),
            "epochProgress": min(max(progress, 0), 100),  # Ensure between 0-100
            "timeLeftInEpoch": max((slots_in_epoch - slot_index) * 0.4, 0)  # 0.4 seconds per slot
        }
        logger.info("Returning epoch info: %s", epoch_info)
        return epoch_info
    except Exception as e:
        logger.error(f"Error getting epoch info: {e}", exc_info=True)
        return None

def background_update():
    """Background task to update validator data"""
    while True:
        try:
            logger.info("Updating validator data in background")
            data = get_validator_info()
            if data:
                # Add KOII price
                data['koiiPrice'] = get_koii_price()
                # Add epoch information
                data['epochInfo'] = get_epoch_info()
                # Store in database
                store_latest_data(data)
            time.sleep(30)  # Update every 30 seconds
        except Exception as e:
            logger.error(f"Error in background update: {e}")
            time.sleep(5)  # Wait before retrying on error

def init_app():
    """Initialize the application"""
    init_db()
    thread = threading.Thread(target=background_update, daemon=True)
    thread.start()
    logger.info("Background update thread started")

# Remove @app.before_first_request
# Start background update thread when app starts
with app.app_context():
    init_app()

@app.route('/')
def index():
    return render_template('index.html', config=Config.to_dict())

@app.route('/api/nodes')
def get_nodes():
    try:
        # First try to get cached data from database
        data = get_latest_data()
        if data:
            return jsonify(data)
            
        # If no cached data, fetch fresh data
        data = get_validator_info()
        if not data:
            return jsonify({'error': 'Failed to fetch data'}), 500
            
        # Add additional data
        data['koiiPrice'] = get_koii_price()
        data['epochInfo'] = get_epoch_info()
        
        # Store in database for next time
        store_latest_data(data)
        
        return jsonify(data)
    except Exception as e:
        logger.error(f"Error in /api/nodes endpoint: {e}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.utcnow().isoformat(),
        'cache_status': {
            'last_update': datetime.fromtimestamp(last_cache_time).isoformat() if last_cache_time else None,
            'ttl': CACHE_TTL
        }
    })

@app.route('/staking')
def staking():
    """Render the staking page"""
    try:
        # Get validator data for the staking form
        validators = get_validator_info()
        if not validators:
            return render_template('staking.html', validators=[])
        
        # Process validators for the staking form
        processed_validators = []
        for validator in validators.get('validators', []):
            processed_validators.append({
                'identity_pubkey': validator.get('identity_pubkey', ''),
                'vote_pubkey': validator.get('vote_pubkey', ''),
                'commission': validator.get('commission', 0),
                'stake': validator.get('stake', 0),
                'apr': validator.get('apr', 0)
            })
        
        return render_template('staking.html', validators=processed_validators)
    except Exception as e:
        logger.error(f"Error rendering staking page: {e}")
        return render_template('staking.html', validators=[])

@app.route('/api/stake', methods=['POST'])
def stake():
    """Handle stake transaction"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        validator_pubkey = data.get('validator_pubkey')
        amount = data.get('amount')
        
        if not validator_pubkey or not amount:
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400
        
        # Create stake transaction
        transaction = create_stake_transaction(validator_pubkey, amount)
        
        return jsonify({
            'success': True,
            'transaction': transaction
        })
    except Exception as e:
        logger.error(f"Error creating stake transaction: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/unstake', methods=['POST'])
def unstake():
    """Handle unstake transaction"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        validator_pubkey = data.get('validator_pubkey')
        
        if not validator_pubkey:
            return jsonify({'success': False, 'error': 'Missing validator pubkey'}), 400
        
        # Create unstake transaction
        transaction = create_unstake_transaction(validator_pubkey)
        
        return jsonify({
            'success': True,
            'transaction': transaction
        })
    except Exception as e:
        logger.error(f"Error creating unstake transaction: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/send-transaction', methods=['POST'])
def send_transaction():
    """Send a signed transaction to the network"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        signed_transaction = data.get('signed_transaction')
        
        if not signed_transaction:
            return jsonify({'success': False, 'error': 'Missing signed transaction'}), 400
        
        # Send transaction to the network
        result = send_transaction_to_network(signed_transaction)
        
        return jsonify({
            'success': True,
            'result': result
        })
    except Exception as e:
        logger.error(f"Error sending transaction: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def create_stake_transaction(validator_pubkey: str, amount: float) -> dict:
    """Create a stake transaction"""
    try:
        # Convert amount to lamports
        lamports = int(amount * 1e9)  # 1 KOII = 1e9 lamports
        
        # Create stake transaction
        transaction = {
            'type': 'stake',
            'validator_pubkey': validator_pubkey,
            'amount': lamports,
            'timestamp': int(time.time())
        }
        
        return transaction
    except Exception as e:
        logger.error(f"Error creating stake transaction: {e}")
        raise

def create_unstake_transaction(validator_pubkey: str) -> dict:
    """Create an unstake transaction"""
    try:
        # Create unstake transaction
        transaction = {
            'type': 'unstake',
            'validator_pubkey': validator_pubkey,
            'timestamp': int(time.time())
        }
        
        return transaction
    except Exception as e:
        logger.error(f"Error creating unstake transaction: {e}")
        raise

def send_transaction_to_network(signed_transaction: dict) -> dict:
    """Send a signed transaction to the network"""
    try:
        # Make RPC call to send transaction
        response = requests.post(
            os.getenv('KOII_RPC_URL'),
            json={
                'jsonrpc': '2.0',
                'id': 1,
                'method': 'sendTransaction',
                'params': [signed_transaction]
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"RPC request failed: {response.text}")
        
        result = response.json()
        if 'error' in result:
            raise Exception(f"RPC error: {result['error']}")
        
        return result['result']
    except Exception as e:
        logger.error(f"Error sending transaction to network: {e}")
        raise

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True) 