#!/usr/bin/env python3
"""
Script to help extract Lisa token from browser and test it
"""

import requests
import json

def test_token(token):
    """Test if a Lisa token is valid"""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    try:
        # Test with a simple endpoint
        response = requests.get(
            'https://admin.lisaapp.net/v1/user/profile',
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            print("✅ Token is valid!")
            print(f"Response: {response.json()}")
            return True
        else:
            print(f"❌ Token validation failed: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing token: {str(e)}")
        return False

def main():
    print("🔑 Lisa Token Helper")
    print("=" * 50)
    print()
    print("To get your Lisa token:")
    print("1. Open Lisa app in browser")
    print("2. Press F12 to open Developer Tools")
    print("3. Go to Application/Storage tab")
    print("4. Look for 'lisa_access' in Local Storage")
    print("5. Copy the token value")
    print()
    
    token = input("Paste your Lisa token here: ").strip()
    
    if not token:
        print("❌ No token provided")
        return
    
    print(f"\nTesting token: {token[:20]}...")
    
    if test_token(token):
        print("\n🎉 Token is working! You can now use it in your API calls.")
        print("\nExample usage:")
        print("curl -X POST http://127.0.0.1:5001/generate-and-create-lisa-course \\")
        print("  -F \"pdf_file=@your_file.pdf\" \\")
        print("  -F \"org_id=6511358aa1964e1f8da51e86\" \\")
        print("  -F \"uid=C_V8JOP-202506261304\" \\")
        print(f"  -F \"authorization_token={token}\"")
    else:
        print("\n❌ Token is not valid. Please check:")
        print("- Token is copied correctly")
        print("- Token hasn't expired")
        print("- You have proper permissions")

if __name__ == "__main__":
    main() 