# Screenshot SCP Uploader Configuration
# Copy this file to config.py and fill in your actual values
from pathlib import Path

# SSH Configuration
REMOTE_HOST = "your-server.com"
REMOTE_USER = "username"
REMOTE_PATH = "/path/to/screenshots/"

# SSH Key Paths (adjust for your system)
# Windows: Path.home() / ".ssh" / "id_rsa"
# Mac/Linux: Path.home() / ".ssh" / "id_rsa"
SSH_KEY_PATH = Path.home() / ".ssh" / "id_rsa"

# Optional: Known hosts file location
KNOWN_HOSTS_PATH = Path.home() / ".ssh" / "known_hosts"

# Application Settings
JPEG_QUALITY = 85
CHECK_INTERVAL = 0.5  # seconds
THUMBNAIL_SIZE = (128, 128)