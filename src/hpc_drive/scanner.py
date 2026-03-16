import hashlib
import httpx
import logging
from fastapi import HTTPException
from hpc_drive.models import ProcessStatus
from hpc_drive.config import settings
import os

logger = logging.getLogger(__name__)

# Free Tier allows 4 requests per minute
VIRUSTOTAL_API_KEY = os.getenv("VIRUSTOTAL_API_KEY", "")
VIRUSTOTAL_URL = "https://www.virustotal.com/api/v3/files/"

def check_hash_virustotal(file_hash: str) -> ProcessStatus:
    """
    Checks the file against VirusTotal using its SHA-256 hash.
    Returns:
    - ProcessStatus.READY if safe
    - ProcessStatus.INFECTED if malicious
    - ProcessStatus.SCAN_PENDING if rate limited or zero-day (hash not found)
    """
    if not VIRUSTOTAL_API_KEY:
        logger.warning("VIRUSTOTAL_API_KEY not set. Skipping malware scan.")
        return ProcessStatus.READY

    headers = {
        "x-apikey": VIRUSTOTAL_API_KEY
    }

    try:
        response = httpx.get(f"{VIRUSTOTAL_URL}{file_hash}", headers=headers, timeout=5.0)
        
        if response.status_code == 200:
            data = response.json()
            stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
            malicious = stats.get("malicious", 0)
            suspicious = stats.get("suspicious", 0)
            
            if malicious > 0 or suspicious > 0:
                logger.warning(f"Malware detected for hash {file_hash}: {malicious} malicious, {suspicious} suspicious")
                return ProcessStatus.INFECTED
            return ProcessStatus.READY
            
        elif response.status_code == 404:
            # Zero-day or unknown file. Tag as SCAN_PENDING
            logger.info(f"Hash {file_hash} not found on VirusTotal. Tagging as SCAN_PENDING.")
            return ProcessStatus.SCAN_PENDING
            
        elif response.status_code == 429:
            # Rate limited
            logger.warning("VirusTotal API rate limit exceeded. Tagging as SCAN_PENDING.")
            return ProcessStatus.SCAN_PENDING
            
        else:
            logger.error(f"VirusTotal API unexpected status: {response.status_code}")
            return ProcessStatus.SCAN_PENDING

    except httpx.RequestError as e:
        logger.error(f"VirusTotal API Request failed: {str(e)}")
        return ProcessStatus.SCAN_PENDING
