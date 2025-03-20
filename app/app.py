from flask import Flask, render_template, jsonify
import requests
import json
from datetime import datetime
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

def calculate_validator_metrics(validator: Dict[str, Any], block_production: Dict[str, List[int]]) -> Dict[str, Any]:
    try:
        vote_pubkey = str(validator.get("votePubkey", ""))
        identity_pubkey = str(validator.get("nodePubkey", vote_pubkey))
        stake = int(validator.get("activatedStake", 0))
        
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
            'delinquent': False
        }
    except Exception as e:
        logger.error(f"Error calculating metrics for validator {vote_pubkey}: {e}", exc_info=True)
        return None

def get_validator_info() -> Optional[Dict[str, Any]]:
    try:
        # Check cache first
        cached_data = get_cached_data()
        if cached_data:
            logger.info("Returning cached validator data")
            return cached_data

        if not Config.KOII_RPC_URL:
            logger.error("KOII_RPC_URL is not configured")
            return None

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
        
        # Process validators
        processed_validators = []
        total_active_stake = 0
        total_current_stake = 0
        total_delinquent_stake = 0
        total_rewards = 0
        
        # Process current validators
        for validator in current_validators:
            metrics = calculate_validator_metrics(validator, block_production)
            if metrics:
                metrics['delinquent'] = False
                processed_validators.append(metrics)
                total_active_stake += metrics['activatedStake']
                total_current_stake += metrics['activatedStake']
                
                # Calculate rewards from epoch credits
                epoch_credits = validator.get("epochCredits", [])
                if len(epoch_credits) >= 3:  # Need at least 3 epochs for previous epoch calculation
                    previous_epoch = epoch_credits[-2]
                    two_epochs_ago = epoch_credits[-3]
                    rewards = previous_epoch[1] - two_epochs_ago[1]  # Use credits from previous epoch
                    total_rewards += rewards
        
        # Process delinquent validators
        for validator in delinquent_validators:
            metrics = calculate_validator_metrics(validator, block_production)
            if metrics:
                metrics['delinquent'] = True
                processed_validators.append(metrics)
                total_delinquent_stake += metrics['activatedStake']
                total_current_stake += metrics['activatedStake']
        
        # Calculate Network APR for Koii Network
        active_validators_count = len([v for v in processed_validators if not v['delinquent']])
        if active_validators_count > 0 and total_active_stake > 0:
            # Calculate total rewards from the previous epoch
            total_epoch_rewards = 0
            
            # Calculate rewards from the previous epoch
            for validator in current_validators:
                epoch_credits = validator.get("epochCredits", [])
                if len(epoch_credits) >= 2:  # Need at least 2 epochs
                    latest = epoch_credits[-1]
                    previous = epoch_credits[-2]
                    epoch_rewards = latest[1] - previous[1]  # Credits earned in current epoch
                    total_epoch_rewards += epoch_rewards
            
            # Calculate epochs per year (Koii uses 12-hour epochs)
            epochs_per_year = (365 * 24) // 12  # 730 epochs per year
            
            # Calculate APR using the formula: APR = ((Epoch Rewards × Epochs per Year) / Total Stake) × 100
            # Convert total_active_stake from lamports to KOII (1 KOII = 1e9 lamports)
            total_stake_in_koii = total_active_stake / 1e9
            
            if total_stake_in_koii > 0:
                network_apr = ((total_epoch_rewards * epochs_per_year) / total_stake_in_koii) * 100
                
                # Round to 2 decimal places
                network_apr = round(network_apr, 2)
                
                # Log values for debugging
                logger.info(f"APR Calculation: total_epoch_rewards={total_epoch_rewards}, "
                           f"epochs_per_year={epochs_per_year}, "
                           f"total_stake_in_koii={total_stake_in_koii}, "
                           f"network_apr={network_apr}%")
            else:
                network_apr = 0
        else:
            network_apr = 0
        
        # Calculate statistics
        stats = {
            'totalActiveStake': total_active_stake,
            'totalCurrentStake': total_current_stake,
            'totalDelinquentStake': total_delinquent_stake,
            'validators': processed_validators,
            'averageSkipRate': sum(v['skipRate'] for v in processed_validators) / len(processed_validators) if processed_validators else 0,
            'networkApr': network_apr,
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
                    'averageCreditsGrowth': 0
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
        
        # Calculate averages for each version
        for version_stats in stats['stakeByVersion'].values():
            total_validators = version_stats['currentValidators'] + version_stats['delinquentValidators']
            if total_validators > 0:
                version_stats['averageSkipRate'] /= total_validators
                version_stats['averageCreditsGrowth'] /= total_validators
        
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

@app.route('/')
def index():
    return render_template('index.html', config=Config.to_dict())

@app.route('/api/nodes')
def get_nodes():
    try:
        data = get_validator_info()
        if not data:
            return jsonify({'error': 'Failed to fetch data'}), 500
            
        # Add KOII price to the response
        data['koiiPrice'] = get_koii_price()
        
        # Add epoch information
        data['epochInfo'] = get_epoch_info()
        
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True) 