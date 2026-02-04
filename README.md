# Screenshot SCP Uploader

A secure GUI application that monitors your clipboard for screenshots and automatically uploads them to a remote server via SCP.

![Python](https://img.shields.io/badge/python-3.7+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)

## Features

- **Automatic Upload**: Monitors clipboard and uploads screenshots instantly via SCP
- **Secure**: Uses SSH key authentication with password-protected keys
- **GUI Interface**: Visual list of uploaded screenshots with 128x128 thumbnails
- **Smart Clipboard Management**:
  - Copy file paths (quoted if contains spaces)
  - Copy base64 encoded images
  - Copy actual image to clipboard for direct pasting
- **Batch Operations**: Delete all, copy all paths, or manage individually
- **Toggle Controls**: Turn monitoring and auto-copy on/off
- **Keyboard Shortcuts**: Quick actions without using mouse
- **Cross-Platform**: Works on Windows, macOS, and Linux
- **Privacy Focused**: No data retention, passphrase cleared from memory after use

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `D` | Delete last uploaded screenshot |
| `A` | Copy all paths to clipboard |
| `W` | Delete all screenshots |
| `S` | Toggle monitoring on/off |
| `C` | Toggle auto-copy path on/off |
| `Q` | Quit application |

## Installation

### Prerequisites

- Python 3.7 or higher
- SSH access to a remote server
- SSH key pair (password-protected recommended)

### Setup

1. **Clone the repository**:
```bash
git clone https://github.com/stewartcelani/screen2scp.git
cd screen2scp
```

2. **Create virtual environment** (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure the application**:
   - Copy `config.template.py` to `config.py`
   - Edit `config.py` with your settings:

```python
# SSH Configuration
REMOTE_HOST = "your-server.com"
REMOTE_USER = "your-username"
REMOTE_PATH = "/path/to/screenshots/"

# SSH Key Path
SSH_KEY_PATH = Path.home() / ".ssh" / "id_rsa"
```

## Usage

### Run the application:

**Windows**:
```bash
run.bat
```

**macOS/Linux**:
```bash
python screenshot_scp_uploader.py
```

### First Run

1. Enter your SSH key passphrase when prompted (input is hidden)
2. The application connects to your server and starts monitoring
3. Take a screenshot using any tool (Print Screen, Snipping Tool, etc.)
4. The screenshot is automatically uploaded and appears in the GUI list

### GUI Features

Each screenshot row displays:
- **Thumbnail** (128x128)
- **Filename** and timestamp
- **File size**
- **Full remote path**
- **Action buttons**:
  - `Copy Path` - Copy file path to clipboard
  - `Copy Base64` - Copy base64 encoded image
  - `Copy Image` - Copy actual image for direct pasting

### Auto-Copy Toggle

- **ON** (default): Path automatically copied after each upload
- **OFF**: Upload without copying path (use buttons to copy when needed)

Toggle with the `C` key or the "AutoCopy (C)" button.

## Security Features

- **SSH Key Authentication**: No passwords stored in code
- **Passphrase Protection**: Entered at runtime, never saved
- **Memory Safety**: Passphrase cleared from memory after connection
- **Atomic Uploads**: Files uploaded as temp, then renamed (no partial files)
- **Host Key Verification**: SSH host keys verified and cached
- **No Credential Logging**: Sensitive data never written to logs

## Configuration Options

Edit these values in `screenshot_scp_uploader.py` or create a `config.py`:

```python
REMOTE_HOST = "your-server.com"        # SSH server hostname
REMOTE_USER = "username"                # SSH username
REMOTE_PATH = "/path/to/screenshots/"   # Remote directory
SSH_KEY_PATH = Path.home() / ".ssh" / "id_rsa"  # SSH private key
JPEG_QUALITY = 85                       # JPEG compression (1-100)
CHECK_INTERVAL = 0.5                    # Clipboard check interval (seconds)
THUMBNAIL_SIZE = (128, 128)             # Thumbnail dimensions
```

## Platform-Specific Notes

### Windows
- Uses native Windows clipboard API for image copying
- Supports all screenshot tools (Win+Shift+S, Snipping Tool, etc.)

### macOS
- Requires SSH keys in OpenSSH format (not .ppk)
- May need to grant clipboard permissions in System Preferences

### Linux
- Requires `xclip` or `xsel` for clipboard operations
- Install with: `sudo apt-get install xclip`

## Troubleshooting

### "SSH key not found"
- Verify `SSH_KEY_PATH` points to your private key
- Ensure the key file exists and has correct permissions (600)

### "Connection failed"
- Check server hostname and username
- Verify SSH key is added to server's `authorized_keys`
- Ensure the remote directory exists or is creatable

### "Clipboard not working"
- **Windows**: Should work out of the box
- **macOS**: Grant terminal Python clipboard permissions
- **Linux**: Install `xclip` or `xsel`

### Images not uploading
- Check if monitoring is enabled (status shows "[ON]")
- Ensure the screenshot tool actually copies to clipboard
- Try pressing `S` to toggle monitoring off and on again

## Development

### Project Structure
```
screen2scp/
├── screenshot_scp_uploader.py  # Main application
├── requirements.txt            # Python dependencies
├── config.template.py          # Configuration template
├── run.bat                     # Windows launcher
├── .gitignore                  # Git ignore rules
└── README.md                   # This file
```

### Dependencies
- `paramiko>=3.0.0` - SSH/SCP client
- `Pillow>=9.0.0` - Image processing
- `plyer>=2.0.0` - System notifications
- `pyperclip>=1.8.2` - Clipboard operations

## License

MIT License - see LICENSE file for details.

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.

## Support

If you encounter any issues or have questions, please open an issue on GitHub.