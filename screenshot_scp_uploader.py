#!/usr/bin/env python3
"""
Secure Screenshot SCP Uploader with GUI
Monitors clipboard for screenshots and uploads them via SCP to a remote server.
Press 'd' in the GUI window to delete the last uploaded screenshot.
Press 'a' to copy all paths to clipboard.
Press 'w' to delete all screenshots.
Press 's' to toggle monitoring on/off.
"""

import os
import sys
import time
import hashlib
import tempfile
import getpass
import gc
import threading
import queue
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass
from PIL import Image, ImageGrab
import paramiko
from plyer import notification
import pyperclip
import tkinter as tk
from tkinter import ttk

# Configuration - EDIT THESE VALUES FOR YOUR SETUP
REMOTE_HOST = "your-server.com"  # Your SSH server hostname
REMOTE_USER = "username"  # Your SSH username
REMOTE_PATH = "/path/to/screenshots/"  # Remote directory for screenshots
SSH_KEY_PATH = Path.home() / ".ssh" / "id_rsa"  # Path to your SSH private key
KNOWN_HOSTS_PATH = Path.home() / ".ssh" / "known_hosts"  # SSH known hosts file
HASH_TRACKING_FILE = Path(__file__).parent / "uploaded_hashes.txt"
JPEG_QUALITY = 85
CHECK_INTERVAL = 0.5  # seconds
THUMBNAIL_SIZE = (128, 128)  # Larger thumbnails


@dataclass
class ScreenshotRecord:
    """Represents an uploaded screenshot."""
    filename: str
    timestamp: datetime
    size: str
    remote_path: str
    image_hash: str
    thumbnail: Optional[Image.Image] = None


class SecureSCPUploader:
    """Secure screenshot uploader with SCP support."""
    
    def __init__(self, gui_queue: queue.Queue):
        self.ssh_client: Optional[paramiko.SSHClient] = None
        self.sftp_client = None
        self.last_image_hash: Optional[str] = None
        self.uploaded_hashes: set = set()
        self._running = False
        self._monitoring = True  # Toggle for monitoring
        self._copy_path_to_clipboard = True  # Toggle for auto-copying path
        self.gui_queue = gui_queue
        self.upload_history: List[ScreenshotRecord] = []
        
    def load_uploaded_hashes(self):
        """Load set of already uploaded image hashes."""
        if HASH_TRACKING_FILE.exists():
            with open(HASH_TRACKING_FILE, 'r') as f:
                self.uploaded_hashes = set(line.strip() for line in f if line.strip())
    
    def save_uploaded_hash(self, image_hash: str):
        """Save hash of uploaded image to tracking file."""
        self.uploaded_hashes.add(image_hash)
        with open(HASH_TRACKING_FILE, 'a') as f:
            f.write(f"{image_hash}\n")
    
    def calculate_image_hash(self, image: Image.Image) -> str:
        """Calculate MD5 hash of image for duplicate detection."""
        import io
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        return hashlib.md5(buffer.getvalue()).hexdigest()
    
    def create_thumbnail(self, image: Image.Image) -> Image.Image:
        """Create a thumbnail from the image."""
        thumb = image.copy()
        thumb.thumbnail(THUMBNAIL_SIZE)
        return thumb
    
    def connect_ssh(self, passphrase: str):
        """Establish SSH connection with password-protected key."""
        self.ssh_client = paramiko.SSHClient()
        
        # Load known hosts or auto-add on first connection
        if KNOWN_HOSTS_PATH.exists():
            self.ssh_client.load_host_keys(str(KNOWN_HOSTS_PATH))
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        try:
            # Connect with private key and passphrase
            self.ssh_client.connect(
                hostname=REMOTE_HOST,
                username=REMOTE_USER,
                key_filename=str(SSH_KEY_PATH),
                passphrase=passphrase,
                look_for_keys=False,
                allow_agent=False
            )
            
            # Open SFTP session
            self.sftp_client = self.ssh_client.open_sftp()
            
            # Ensure remote directory exists
            try:
                self.sftp_client.stat(REMOTE_PATH)
            except FileNotFoundError:
                self.ssh_client.exec_command(f"mkdir -p {REMOTE_PATH}")
            
            # Save host key for future verification
            if not KNOWN_HOSTS_PATH.exists():
                KNOWN_HOSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.ssh_client.save_host_keys(str(KNOWN_HOSTS_PATH))
            
        except Exception as e:
            raise Exception(f"Connection failed: {e}")
    
    def disconnect(self):
        """Close SSH connection and cleanup."""
        if self.sftp_client:
            self.sftp_client.close()
        if self.ssh_client:
            self.ssh_client.close()
    
    def get_clipboard_image(self) -> Optional[Image.Image]:
        """Get image from clipboard if available."""
        try:
            image = ImageGrab.grabclipboard()
            if isinstance(image, Image.Image):
                return image
        except Exception:
            pass
        return None
    
    def upload_screenshot(self, image: Image.Image) -> Optional[ScreenshotRecord]:
        """Upload screenshot via SCP with atomic temp file approach."""
        try:
            # Generate filename with timestamp
            timestamp = datetime.now()
            filename = f"screenshot_{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            temp_filename = f"{filename}.tmp"
            
            remote_temp_path = f"{REMOTE_PATH}{temp_filename}"
            remote_final_path = f"{REMOTE_PATH}{filename}"
            
            # Create thumbnail before conversion
            thumbnail = self.create_thumbnail(image)
            
            # Convert to JPEG and save to local temp file
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                local_temp_path = tmp_file.name
            
            try:
                # Convert RGBA to RGB if necessary
                if image.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', image.size, (255, 255, 255))
                    background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                    image = background
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # Save as JPEG
                image.save(local_temp_path, 'JPEG', quality=JPEG_QUALITY, optimize=True)
                
                # Get file size
                size_bytes = os.path.getsize(local_temp_path)
                size_str = f"{size_bytes / 1024:.1f} KB"
                
                # Upload to temp location
                self.sftp_client.put(local_temp_path, remote_temp_path)
                
                # Atomic rename on server
                self.sftp_client.rename(remote_temp_path, remote_final_path)
                
                # Copy full path to clipboard (if enabled)
                if self._copy_path_to_clipboard:
                    pyperclip.copy(remote_final_path)
                
                # Create record
                record = ScreenshotRecord(
                    filename=filename,
                    timestamp=timestamp,
                    size=size_str,
                    remote_path=remote_final_path,
                    image_hash=self.calculate_image_hash(image),
                    thumbnail=thumbnail
                )
                
                return record
                
            finally:
                # Cleanup local temp file
                if os.path.exists(local_temp_path):
                    os.unlink(local_temp_path)
                    
        except Exception as e:
            print(f"Upload failed: {e}")
            return None
    
    def delete_screenshot(self, record: ScreenshotRecord) -> bool:
        """Delete a screenshot from the remote server."""
        try:
            self.sftp_client.remove(record.remote_path)
            # Remove from tracking
            if record.image_hash in self.uploaded_hashes:
                self.uploaded_hashes.discard(record.image_hash)
                # Update tracking file
                with open(HASH_TRACKING_FILE, 'w') as f:
                    for h in self.uploaded_hashes:
                        f.write(f"{h}\n")
            return True
        except Exception as e:
            print(f"Delete failed: {e}")
            return False
    
    def notify(self, title: str, message: str, success: bool = True):
        """Show Windows notification."""
        try:
            notification.notify(
                title=title,
                message=message,
                app_name="Screenshot SCP Uploader",
                timeout=3
            )
        except Exception:
            pass
    
    def process_clipboard(self):
        """Check clipboard and process any new screenshot."""
        if not self._monitoring:
            return
            
        image = self.get_clipboard_image()
        if not image:
            return
        
        # Calculate hash
        image_hash = self.calculate_image_hash(image)
        
        # Skip if same as last processed or already uploaded
        if image_hash == self.last_image_hash or image_hash in self.uploaded_hashes:
            return
        
        self.last_image_hash = image_hash
        
        # Upload
        record = self.upload_screenshot(image)
        if record:
            self.save_uploaded_hash(image_hash)
            self.upload_history.insert(0, record)  # Add to beginning
            # Notify GUI
            self.gui_queue.put(('uploaded', record))
            self.notify(
                "Screenshot Uploaded",
                f"{record.filename} - Path copied!",
                success=True
            )
        else:
            self.gui_queue.put(('error', "Upload failed"))
            self.notify(
                "Upload Failed",
                "Could not upload screenshot",
                success=False
            )
        
        # Clear image from memory
        del image
        gc.collect()
    
    def run(self):
        """Main loop - monitor clipboard and upload screenshots."""
        self._running = True
        
        try:
            while self._running:
                self.process_clipboard()
                time.sleep(CHECK_INTERVAL)
        except Exception as e:
            self.gui_queue.put(('error', str(e)))
        finally:
            self._running = False
    
    def stop(self):
        """Stop the monitoring loop."""
        self._running = False
    
    def toggle_monitoring(self):
        """Toggle clipboard monitoring on/off."""
        self._monitoring = not self._monitoring
        return self._monitoring


class ScreenshotUploaderGUI:
    """GUI for the screenshot uploader."""
    
    def __init__(self, uploader: SecureSCPUploader):
        self.uploader = uploader
        self.root = tk.Tk()
        self.root.title("Screenshot SCP Uploader")
        self.root.geometry("1000x800")  # Larger window
        self.root.minsize(800, 600)
        
        # Configure style
        self.style = ttk.Style()
        self.style.configure("Title.TLabel", font=("Helvetica", 16, "bold"))
        self.style.configure("Status.TLabel", font=("Helvetica", 10))
        
        # Thumbnail cache
        self.thumbnail_cache = {}
        self.items_to_delete = []
        
        self.setup_ui()
        
        # Bind keyboard events
        self.root.bind('<Key>', self.on_key_press)
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)
        
        # Update queue check
        self.check_queue()
        
        # Animation timer
        self.animation_active = False
    
    def setup_ui(self):
        """Setup the user interface."""
        # Main container
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Title
        title_frame = ttk.Frame(main_frame)
        title_frame.grid(row=0, column=0, pady=(0, 5), sticky="ew")
        title_frame.columnconfigure(0, weight=1)
        
        title_label = ttk.Label(
            title_frame, 
            text="Screenshot SCP Uploader", 
            style="Title.TLabel"
        )
        title_label.grid(row=0, column=0, sticky="w")
        
        self.connection_label = ttk.Label(
            title_frame,
            text="● Connected",
            foreground="green",
            font=("Helvetica", 10)
        )
        self.connection_label.grid(row=0, column=1, sticky="e")
        
        # Status frame
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=1, column=0, pady=(0, 10), sticky="ew")
        
        self.status_label = ttk.Label(
            status_frame, 
            text="Monitoring clipboard...",
            foreground="gray",
            style="Status.TLabel"
        )
        self.status_label.pack(side=tk.LEFT)
        
        self.monitoring_label = ttk.Label(
            status_frame,
            text="[ON]",
            foreground="green",
            font=("Helvetica", 10, "bold")
        )
        self.monitoring_label.pack(side=tk.LEFT, padx=(10, 0))
        
        # Auto-copy indicator
        self.autocopy_label = ttk.Label(
            status_frame,
            text="| AutoCopy: ON",
            foreground="green",
            font=("Helvetica", 10)
        )
        self.autocopy_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # Instructions
        instructions = ttk.Label(
            status_frame,
            text="D: Delete | A: Copy All | W: Delete All | S: Toggle Monitor | C: Toggle AutoCopy | Q: Quit",
            foreground="gray"
        )
        instructions.pack(side=tk.RIGHT)
        
        # List frame for screenshots
        list_frame = ttk.Frame(main_frame)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)
        
        # Canvas for scrolling
        self.canvas = tk.Canvas(list_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=960)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        
        # Mouse wheel scrolling
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)
        
        # Stats frame
        stats_frame = ttk.Frame(main_frame)
        stats_frame.grid(row=3, column=0, pady=(10, 0), sticky="ew")
        
        self.stats_label = ttk.Label(stats_frame, text="Uploaded: 0 screenshots")
        self.stats_label.pack(side=tk.LEFT)
        
        # Auto-copy toggle button
        self.autocopy_btn = ttk.Button(
            stats_frame,
            text="AutoCopy (C)",
            command=self.toggle_autocopy
        )
        self.autocopy_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Toggle button
        self.toggle_btn = ttk.Button(
            stats_frame,
            text="Toggle Monitor (S)",
            command=self.toggle_monitoring
        )
        self.toggle_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Copy all button
        self.copy_all_btn = ttk.Button(
            stats_frame,
            text="Copy All (A)",
            command=self.copy_all_paths
        )
        self.copy_all_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Delete all button
        self.delete_all_btn = ttk.Button(
            stats_frame,
            text="Delete All (W)",
            command=self.delete_all_screenshots
        )
        self.delete_all_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Delete button
        self.delete_btn = ttk.Button(
            stats_frame,
            text="Delete Last (D)",
            command=self.delete_last_screenshot
        )
        self.delete_btn.pack(side=tk.RIGHT, padx=(5, 0))
        
        # Quit button
        self.quit_btn = ttk.Button(
            stats_frame,
            text="Quit (Q)",
            command=self.quit_app
        )
        self.quit_btn.pack(side=tk.RIGHT)
    
    def on_mousewheel(self, event):
        """Handle mouse wheel scrolling."""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")
    
    def on_key_press(self, event):
        """Handle keyboard events."""
        key = event.char.lower()
        
        if key == 'd':
            self.delete_last_screenshot()
        elif key == 'a':
            self.copy_all_paths()
        elif key == 'w':
            self.delete_all_screenshots()
        elif key == 's':
            self.toggle_monitoring()
        elif key == 'c':
            self.toggle_autocopy()
        elif key == 'q':
            self.quit_app()
    
    def toggle_monitoring(self):
        """Toggle monitoring on/off."""
        is_monitoring = self.uploader.toggle_monitoring()
        if is_monitoring:
            self.monitoring_label.config(text="[ON]", foreground="green")
            self.status_label.config(text="Monitoring clipboard...", foreground="gray")
        else:
            self.monitoring_label.config(text="[OFF]", foreground="red")
            self.status_label.config(text="Monitoring paused", foreground="orange")

    def toggle_autocopy(self):
        """Toggle auto-copy path to clipboard on/off."""
        self.uploader._copy_path_to_clipboard = not self.uploader._copy_path_to_clipboard
        if self.uploader._copy_path_to_clipboard:
            self.autocopy_label.config(text="| AutoCopy: ON", foreground="green")
            self.status_label.config(text="Auto-copy enabled", foreground="green")
        else:
            self.autocopy_label.config(text="| AutoCopy: OFF", foreground="red")
            self.status_label.config(text="Auto-copy disabled", foreground="orange")
        self.root.after(2000, lambda: self.status_label.config(
            text="Monitoring clipboard...",
            foreground="gray"
        ))

    def check_queue(self):
        """Check for messages from the uploader thread."""
        try:
            while True:
                msg_type, data = self.uploader.gui_queue.get_nowait()
                
                if msg_type == 'uploaded':
                    self.add_screenshot_to_list(data)
                elif msg_type == 'error':
                    self.status_label.config(text=f"Error: {data}", foreground="red")
        except queue.Empty:
            pass
        
        # Schedule next check
        self.root.after(100, self.check_queue)
    
    def pil_to_tk(self, pil_image: Image.Image):
        """Convert PIL image to tkinter PhotoImage."""
        from PIL import ImageTk
        return ImageTk.PhotoImage(pil_image)
    
    def add_screenshot_to_list(self, record: ScreenshotRecord):
        """Add a screenshot to the GUI list."""
        # Create frame for this item
        item_frame = ttk.Frame(self.scrollable_frame, padding="10")
        item_frame.pack(fill=tk.X, pady=(0, 2))
        
        # Store reference
        item_frame.record = record
        
        # Thumbnail
        if record.thumbnail:
            tk_thumb = self.pil_to_tk(record.thumbnail)
            self.thumbnail_cache[record.filename] = tk_thumb  # Keep reference
            thumb_label = ttk.Label(item_frame, image=tk_thumb)
            thumb_label.pack(side=tk.LEFT, padx=(0, 15))
        
        # Info frame
        info_frame = ttk.Frame(item_frame)
        info_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Filename
        name_label = ttk.Label(
            info_frame,
            text=record.filename,
            font=("Helvetica", 11, "bold")
        )
        name_label.pack(anchor="w")
        
        # Details
        time_str = record.timestamp.strftime("%H:%M:%S")
        details_text = f"{time_str} | {record.size}"
        details_label = ttk.Label(
            info_frame,
            text=details_text,
            foreground="gray",
            font=("Helvetica", 9)
        )
        details_label.pack(anchor="w")
        
        # Path
        path_label = ttk.Label(
            info_frame,
            text=record.remote_path,
            foreground="blue",
            font=("Helvetica", 8)
        )
        path_label.pack(anchor="w")
        
        # Buttons frame
        buttons_frame = ttk.Frame(item_frame)
        buttons_frame.pack(side=tk.RIGHT, padx=(10, 0))
        
        # Copy path button
        copy_path_btn = ttk.Button(
            buttons_frame,
            text="Copy Path",
            command=lambda r=record: self.copy_single_path(r)
        )
        copy_path_btn.pack(side=tk.TOP, pady=(0, 5))
        
        # Copy base64 button
        copy_b64_btn = ttk.Button(
            buttons_frame,
            text="Copy Base64",
            command=lambda r=record: self.copy_base64(r)
        )
        copy_b64_btn.pack(side=tk.TOP, pady=(0, 5))
        
        # Copy image button
        copy_image_btn = ttk.Button(
            buttons_frame,
            text="Copy Image",
            command=lambda r=record: self.copy_image_to_clipboard(r)
        )
        copy_image_btn.pack(side=tk.TOP)
        
        # Separator
        ttk.Separator(self.scrollable_frame, orient='horizontal').pack(fill=tk.X, pady=(2, 0))
        
        # Update status
        if self.uploader._copy_path_to_clipboard:
            self.status_label.config(
                text="Path copied to clipboard! ✓",
                foreground="green"
            )
        else:
            self.status_label.config(
                text=f"Uploaded: {record.filename}",
                foreground="green"
            )
        self.root.after(2000, lambda: self.status_label.config(
            text="Monitoring clipboard...",
            foreground="gray"
        ))
        
        # Update stats
        count = len(self.uploader.upload_history)
        self.stats_label.config(text=f"Uploaded: {count} screenshot{'s' if count != 1 else ''}")
        
        # Scroll to top
        self.canvas.yview_moveto(0)
    
    def copy_single_path(self, record: ScreenshotRecord):
        """Copy a single screenshot path to clipboard."""
        path = record.remote_path
        if ' ' in path:
            path = f'"{path}"'
        pyperclip.copy(path)
        
        self.status_label.config(
            text=f"Path copied: {record.filename} ✓",
            foreground="green"
        )
        self.root.after(2000, lambda: self.status_label.config(
            text="Monitoring clipboard...",
            foreground="gray"
        ))
    
    def copy_base64(self, record: ScreenshotRecord):
        """Copy screenshot as base64 to clipboard."""
        try:
            # Download the file from server temporarily
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                local_path = tmp_file.name
            
            try:
                # Download from server
                self.uploader.sftp_client.get(record.remote_path, local_path)
                
                # Convert to base64
                import base64
                with open(local_path, 'rb') as f:
                    image_data = f.read()
                    base64_string = base64.b64encode(image_data).decode('utf-8')
                
                # Copy to clipboard
                pyperclip.copy(base64_string)
                
                # Show size
                size_kb = len(base64_string) / 1024
                self.status_label.config(
                    text=f"Base64 copied: {record.filename} ({size_kb:.1f} KB) ✓",
                    foreground="green"
                )
                self.root.after(3000, lambda: self.status_label.config(
                    text="Monitoring clipboard...",
                    foreground="gray"
                ))
                
            finally:
                # Cleanup
                if os.path.exists(local_path):
                    os.unlink(local_path)
                    
        except Exception as e:
            self.status_label.config(text=f"Base64 copy failed: {e}", foreground="red")
            self.root.after(3000, lambda: self.status_label.config(
                text="Monitoring clipboard...",
                foreground="gray"
            ))
    
    def copy_image_to_clipboard(self, record: ScreenshotRecord):
        """Copy the actual image to clipboard so it can be pasted into applications."""
        try:
            # Download the file from server temporarily
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_file:
                local_path = tmp_file.name
            
            try:
                # Download from server
                self.uploader.sftp_client.get(record.remote_path, local_path)
                
                # Open image
                from PIL import Image
                image = Image.open(local_path)
                
                # Copy to clipboard using Windows-specific method
                # This allows pasting directly into web apps like Claude
                import io
                
                # Convert to DIB format (Device Independent Bitmap) for clipboard
                output = io.BytesIO()
                image.convert("RGB").save(output, "BMP")
                data = output.getvalue()[14:]  # Remove BMP header to get DIB
                output.close()
                
                # Windows clipboard API
                import ctypes
                
                # Allocate global memory
                GHND = 0x0042
                CF_DIB = 8
                
                # Get handle to global memory
                handle = ctypes.windll.kernel32.GlobalAlloc(GHND, len(data))
                locked_data = ctypes.windll.kernel32.GlobalLock(handle)
                
                # Copy data
                ctypes.memmove(locked_data, data, len(data))
                ctypes.windll.kernel32.GlobalUnlock(handle)
                
                # Open clipboard and set data
                if ctypes.windll.user32.OpenClipboard(0):
                    ctypes.windll.user32.EmptyClipboard()
                    ctypes.windll.user32.SetClipboardData(CF_DIB, handle)
                    ctypes.windll.user32.CloseClipboard()
                
                self.status_label.config(
                    text=f"Image copied: {record.filename} - Ready to paste! ✓",
                    foreground="green"
                )
                self.root.after(3000, lambda: self.status_label.config(
                    text="Monitoring clipboard...",
                    foreground="gray"
                ))
                
            finally:
                # Cleanup
                if os.path.exists(local_path):
                    os.unlink(local_path)
                    
        except Exception as e:
            self.status_label.config(text=f"Image copy failed: {e}", foreground="red")
            self.root.after(3000, lambda: self.status_label.config(
                text="Monitoring clipboard...",
                foreground="gray"
            ))

    def copy_all_paths(self):
        """Copy all screenshot paths to clipboard, quoted if they contain spaces."""
        if not self.uploader.upload_history:
            self.status_label.config(text="No screenshots to copy", foreground="orange")
            self.root.after(1500, lambda: self.status_label.config(
                text="Monitoring clipboard...",
                foreground="gray"
            ))
            return
        
        # Format paths with quotes if they contain spaces
        formatted_paths = []
        for record in self.uploader.upload_history:
            path = record.remote_path
            if ' ' in path:
                formatted_paths.append(f'"{path}"')
            else:
                formatted_paths.append(path)
        
        # Join with spaces
        all_paths = ' '.join(formatted_paths)
        
        # Copy to clipboard
        pyperclip.copy(all_paths)
        
        # Update status
        count = len(self.uploader.upload_history)
        self.status_label.config(
            text=f"Copied {count} path{'s' if count != 1 else ''} to clipboard! ✓",
            foreground="green"
        )
        self.root.after(2000, lambda: self.status_label.config(
            text="Monitoring clipboard...",
            foreground="gray"
        ))
        
        self.uploader.notify(
            "Paths Copied",
            f"{count} screenshot path{'s' if count != 1 else ''} copied to clipboard",
            success=True
        )
    
    def delete_last_screenshot(self):
        """Delete the most recently uploaded screenshot with animation."""
        if not self.uploader.upload_history:
            self.status_label.config(text="No screenshots to delete", foreground="orange")
            self.root.after(1500, lambda: self.status_label.config(
                text="Monitoring clipboard...",
                foreground="gray"
            ))
            return
        
        # Get last uploaded (first in list since we insert at beginning)
        record = self.uploader.upload_history[0]
        
        # Find the frame for this record
        for widget in self.scrollable_frame.winfo_children():
            if isinstance(widget, ttk.Frame) and hasattr(widget, 'record'):
                if widget.record.filename == record.filename:
                    self.animate_delete(widget, record)
                    break
    
    def animate_delete(self, widget, record):
        """Animate the deletion of a screenshot row."""
        # Flash red
        widget.configure(style='Red.TFrame')
        self.root.after(100, lambda: self.animate_delete_step2(widget, record))
    
    def animate_delete_step2(self, widget, record):
        """Step 2 of delete animation."""
        widget.configure(style='TFrame')
        self.root.after(100, lambda: self.animate_delete_step3(widget, record))
    
    def animate_delete_step3(self, widget, record):
        """Step 3 of delete animation - complete deletion."""
        # Complete the deletion
        self.complete_delete(widget, record)
    
    def complete_delete(self, widget, record):
        """Complete the deletion after animation."""
        # Delete from server
        if self.uploader.delete_screenshot(record):
            # Remove from history
            self.uploader.upload_history.remove(record)
            
            # Destroy widget and its separator
            widget.destroy()
            
            # Find and destroy the separator after this widget
            children = self.scrollable_frame.winfo_children()
            for i, child in enumerate(children):
                if isinstance(child, ttk.Separator):
                    child.destroy()
                    break
            
            # Update stats
            count = len(self.uploader.upload_history)
            self.stats_label.config(text=f"Uploaded: {count} screenshot{'s' if count != 1 else ''}")
            self.status_label.config(text=f"Deleted: {record.filename}", foreground="blue")
            self.root.after(1500, lambda: self.status_label.config(
                text="Monitoring clipboard...",
                foreground="gray"
            ))
            
            self.uploader.notify(
                "Screenshot Deleted",
                record.filename,
                success=True
            )
        else:
            self.status_label.config(text="Delete failed", foreground="red")
            self.root.after(2000, lambda: self.status_label.config(
                text="Monitoring clipboard...",
                foreground="gray"
            ))
    
    def delete_all_screenshots(self):
        """Delete all uploaded screenshots."""
        if not self.uploader.upload_history:
            self.status_label.config(text="No screenshots to delete", foreground="orange")
            self.root.after(1500, lambda: self.status_label.config(
                text="Monitoring clipboard...",
                foreground="gray"
            ))
            return
        
        count = len(self.uploader.upload_history)
        self.status_label.config(text=f"Deleting all {count} screenshots...", foreground="orange")
        self.root.update()
        
        # Delete all records
        deleted = 0
        failed = 0
        
        # Work with a copy since we'll be modifying the list
        records_to_delete = self.uploader.upload_history.copy()
        
        for record in records_to_delete:
            if self.uploader.delete_screenshot(record):
                deleted += 1
            else:
                failed += 1
        
        # Clear the history list
        self.uploader.upload_history.clear()
        
        # Clear the GUI
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Clear thumbnail cache
        self.thumbnail_cache.clear()
        
        # Update stats
        self.stats_label.config(text="Uploaded: 0 screenshots")
        
        if failed == 0:
            self.status_label.config(
                text=f"Deleted all {deleted} screenshot{'s' if deleted != 1 else ''}",
                foreground="blue"
            )
            self.uploader.notify(
                "All Screenshots Deleted",
                f"{deleted} screenshot{'s' if deleted != 1 else ''} removed",
                success=True
            )
        else:
            self.status_label.config(
                text=f"Deleted {deleted}, failed {failed}",
                foreground="orange"
            )
        
        self.root.after(2000, lambda: self.status_label.config(
            text="Monitoring clipboard...",
            foreground="gray"
        ))
    
    def quit_app(self):
        """Quit the application."""
        self.uploader.stop()
        self.root.quit()
        self.root.destroy()
    
    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()


def main():
    """Main entry point."""
    # Check SSH key exists
    if not SSH_KEY_PATH.exists():
        print(f"Error: SSH key not found at {SSH_KEY_PATH}")
        print("Please ensure your SSH key is at ~/.ssh/hetzner_key")
        sys.exit(1)
    
    # Get passphrase securely
    print("Enter SSH key passphrase (input hidden): ", end='', flush=True)
    passphrase = getpass.getpass('')
    
    if not passphrase:
        print("Error: Passphrase is required")
        sys.exit(1)
    
    # Create queue for GUI communication
    gui_queue = queue.Queue()
    
    # Create uploader
    uploader = SecureSCPUploader(gui_queue)
    
    try:
        # Load tracking data
        uploader.load_uploaded_hashes()
        
        # Connect to server
        uploader.connect_ssh(passphrase)
        
        # Clear passphrase from memory
        passphrase = '0' * len(passphrase)
        del passphrase
        gc.collect()
        
        # Start monitoring in background thread
        monitor_thread = threading.Thread(target=uploader.run, daemon=True)
        monitor_thread.start()
        
        # Create and run GUI
        gui = ScreenshotUploaderGUI(uploader)
        gui.run()
        
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        uploader.stop()
        uploader.disconnect()


if __name__ == "__main__":
    main()