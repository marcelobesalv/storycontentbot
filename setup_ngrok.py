#!/usr/bin/env python3
"""
Setup ngrok authentication token
"""

from pyngrok import ngrok, conf
import sys

def setup_ngrok_auth(auth_token):
    """Setup ngrok authentication token"""
    try:
        print("🔧 Setting up ngrok authentication...")
        
        # Set the auth token
        ngrok.set_auth_token(auth_token)
        
        print("✅ Ngrok auth token configured successfully!")
        print("🚀 You can now use: python web_app.py --public")
        
        return True
        
    except Exception as e:
        print(f"❌ Error setting up ngrok: {e}")
        return False

def test_ngrok():
    """Test if ngrok is working"""
    try:
        print("🧪 Testing ngrok connection...")
        
        # Try to create a test tunnel
        tunnel = ngrok.connect(8000)
        print(f"✅ Test tunnel created: {tunnel.public_url}")
        
        # Close the test tunnel
        ngrok.disconnect(tunnel.public_url)
        print("🔧 Test tunnel closed")
        
        return True
        
    except Exception as e:
        print(f"❌ Ngrok test failed: {e}")
        return False

if __name__ == "__main__":
    # Your auth token
    auth_token = "33yw7qVV0Dud3l4FZZ5p43kvpEz_7BHzPyzbvyLzCVRWTe9rc"
    
    print("🌐 Ngrok Setup Tool")
    print("=" * 50)
    
    # Setup auth token
    if setup_ngrok_auth(auth_token):
        # Test the connection
        test_ngrok()
        print("\n🎉 Setup complete! You can now use internet access.")
    else:
        print("\n❌ Setup failed. Check your internet connection and try again.")