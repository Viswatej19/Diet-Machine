import os
import asyncio
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

def test_goals():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    client = create_client(url, key)

    user_id = "2fb71064-96aa-45a5-823b-bee46a8f5a6c" # Assuming the user ID we saw earlier

    print("Logging in first...")
    client.auth.sign_in_with_password({"email": "vissu1521@gmail.com", "password": "1234567"})
    
    payload = {
        "user_id": user_id,
        "calorie_target": 1800,
        "protein_target": 130,
        "diet_type": "non-veg",
        "weight": 75.0,
        "goal": "maintenance",
    }
    print("Testing user_preferences upsert...")
    try:
        res = client.table("user_preferences").upsert(payload, on_conflict="user_id").execute()
        print("Success user_preferences:", res)
    except Exception as e:
        print("Error user_preferences:", e)

    payload_goals = {
        "user_id": user_id,
        "calories": 1800,
        "protein": 130,
        "fiber": 30,
    }
    print("\nTesting user_goals upsert...")
    try:
        res2 = client.table("user_goals").upsert(payload_goals, on_conflict="user_id").execute()
        print("Success user_goals:", res2)
    except Exception as e:
        print("Error user_goals:", e)

if __name__ == "__main__":
    test_goals()
