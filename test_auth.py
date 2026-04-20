import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def test_auth():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    client = create_client(url, key)

    email = "vissu1521@gmail.com"
    password = "1234567"
    
    print("--- Testing Sign Up ---")
    try:
        res = client.auth.sign_up({"email": email, "password": password})
        print(f"Signup Result: {res}")
    except Exception as e:
        print(f"Signup Exception: {e}")

    print("\n--- Testing Sign In ---")
    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
        print(f"Signin Result: {res}")
    except Exception as e:
        print(f"Signin Exception: {e}")

if __name__ == "__main__":
    test_auth()
