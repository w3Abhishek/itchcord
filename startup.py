import sys
import os
import platform
import logging

log = logging.getLogger(__name__)

APP_NAME = "itchcord"

def get_executable_path():
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        return os.path.abspath(sys.argv[0])

def is_startup_enabled() -> bool:
    system = platform.system()
    try:
        if system == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
            try:
                val, _ = winreg.QueryValueEx(key, APP_NAME)
                # Just check if it's there
                return True
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        elif system == "Linux":
            desktop_file = os.path.expanduser(f"~/.config/autostart/{APP_NAME}.desktop")
            return os.path.exists(desktop_file)
        elif system == "Darwin":
            plist_file = os.path.expanduser(f"~/Library/LaunchAgents/com.w3Abhishek.{APP_NAME}.plist")
            return os.path.exists(plist_file)
    except Exception as e:
        log.error(f"Error checking startup status: {e}")
    return False

def set_startup(enable: bool):
    system = platform.system()
    exe_path = get_executable_path()
    
    try:
        if system == "Windows":
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
            if enable:
                # Use quotes around the path to handle spaces
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
            
        elif system == "Linux":
            autostart_dir = os.path.expanduser("~/.config/autostart")
            desktop_file = os.path.join(autostart_dir, f"{APP_NAME}.desktop")
            if enable:
                os.makedirs(autostart_dir, exist_ok=True)
                with open(desktop_file, "w") as f:
                    f.write(f"[Desktop Entry]\nType=Application\nName={APP_NAME}\nExec={exe_path}\nTerminal=false\n")
            else:
                if os.path.exists(desktop_file):
                    os.remove(desktop_file)
                    
        elif system == "Darwin":
            launch_agents_dir = os.path.expanduser("~/Library/LaunchAgents")
            plist_file = os.path.join(launch_agents_dir, f"com.w3Abhishek.{APP_NAME}.plist")
            if enable:
                os.makedirs(launch_agents_dir, exist_ok=True)
                plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.w3Abhishek.{APP_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{exe_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"""
                with open(plist_file, "w") as f:
                    f.write(plist_content)
            else:
                if os.path.exists(plist_file):
                    os.remove(plist_file)
                    
        log.info(f"Startup enabled set to {enable} for {system}")
    except Exception as e:
        log.error(f"Error setting startup: {e}")
