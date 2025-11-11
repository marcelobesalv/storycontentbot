#!/usr/bin/env python3
"""
Password Management Utility for Content Creator Web Interface
"""
import json
import hashlib
import getpass
import os

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def load_config():
    """Load config.json"""
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("❌ config.json not found!")
        return None
    except json.JSONDecodeError:
        print("❌ Invalid JSON in config.json!")
        return None

def save_config(config):
    """Save config.json"""
    try:
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        print(f"❌ Error saving config: {e}")
        return False

def main():
    print("🔐 Content Creator - Password Management")
    print("=" * 50)
    
    config = load_config()
    if not config:
        return
    
    # Ensure web_auth section exists
    if 'web_auth' not in config:
        config['web_auth'] = {}
    
    print("\nCurrent settings:")
    print(f"Username: {config['web_auth'].get('username', 'admin')}")
    print(f"Auth enabled: {config['web_auth'].get('enabled', True)}")
    
    print("\nOptions:")
    print("1. Change username")
    print("2. Change password")
    print("3. Enable/disable authentication")
    print("4. Show current settings")
    print("5. Reset to defaults")
    print("0. Exit")
    
    while True:
        choice = input("\nEnter your choice (0-5): ").strip()
        
        if choice == '0':
            print("👋 Goodbye!")
            break
            
        elif choice == '1':
            new_username = input("Enter new username: ").strip()
            if new_username:
                config['web_auth']['username'] = new_username
                if save_config(config):
                    print(f"✅ Username changed to: {new_username}")
                else:
                    print("❌ Failed to save config")
            else:
                print("❌ Username cannot be empty")
                
        elif choice == '2':
            print("\nChanging password...")
            password1 = getpass.getpass("Enter new password: ")
            password2 = getpass.getpass("Confirm new password: ")
            
            if password1 != password2:
                print("❌ Passwords don't match!")
                continue
            
            if len(password1) < 6:
                print("❌ Password must be at least 6 characters!")
                continue
            
            config['web_auth']['password_hash'] = hash_password(password1)
            if save_config(config):
                print("✅ Password changed successfully!")
            else:
                print("❌ Failed to save config")
                
        elif choice == '3':
            current = config['web_auth'].get('enabled', True)
            new_state = not current
            config['web_auth']['enabled'] = new_state
            
            if save_config(config):
                status = "enabled" if new_state else "disabled"
                print(f"✅ Authentication {status}")
                if not new_state:
                    print("⚠️  WARNING: Authentication is now disabled!")
            else:
                print("❌ Failed to save config")
                
        elif choice == '4':
            print("\n📋 Current Settings:")
            print(f"Username: {config['web_auth'].get('username', 'admin')}")
            print(f"Auth enabled: {config['web_auth'].get('enabled', True)}")
            print(f"Password hash: {config['web_auth'].get('password_hash', 'Not set')[:20]}...")
            
        elif choice == '5':
            confirm = input("Reset to defaults? (yes/no): ").lower()
            if confirm == 'yes':
                config['web_auth'] = {
                    'enabled': True,
                    'username': 'admin',
                    'password_hash': hash_password('admin123')
                }
                if save_config(config):
                    print("✅ Reset to defaults:")
                    print("   Username: admin")
                    print("   Password: admin123")
                else:
                    print("❌ Failed to save config")
            else:
                print("❌ Reset cancelled")
                
        else:
            print("❌ Invalid choice!")

if __name__ == '__main__':
    main()