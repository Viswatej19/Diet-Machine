import os
import asyncio
from dotenv import load_dotenv
from openai import AsyncOpenAI, AuthenticationError

load_dotenv()

async def test_key():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("ERROR: No OPENAI_API_KEY found in .env")
        return
        
    print(f"Key loaded successfully. First 10 chars: {key[:10]}...")
    if " " in key:
        print("WARNING: There is a space in your API key string!")
    if key.startswith('"') or key.startswith("'"):
        print("WARNING: Key starts with a quote mark!")
        
    client = AsyncOpenAI(api_key=key)
    try:
        models = await client.models.list()
        print("SUCCESS! API Key is fully working and authenticated.")
    except AuthenticationError as e:
        print(f"AUTHENTICATION ERROR FROM OPENAI: {e}")
    except Exception as e:
        print(f"OTHER ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_key())
