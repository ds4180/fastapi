import requests
import json

BASE_URL = "http://localhost:8000/api/users"

def test_session_logic():
    print("Test Start: Intelligent Session Slot Management")

    # 0. Create User
    requests.post(f"{BASE_URL}/create", json={
        "username": "testuser",
        "password1": "password123",
        "password2": "password123",
        "email": "test@example.com"
    })

    # 1. MOBILE Login
    print("1. [MOBILE] Login...")
    r1 = requests.post(f"{BASE_URL}/login?device_category=MOBILE", data={"username": "testuser", "password": "password123"})
    token_mobile = r1.json().get("access_token")

    # 2. WORKSPACE 1 Login
    print("2. [WORKSPACE 1] Login...")
    r2 = requests.post(f"{BASE_URL}/login?device_category=WORKSPACE", data={"username": "testuser", "password": "password123"})
    token_pc1 = r2.json().get("access_token")

    # 3. WORKSPACE 2 Login (Kick WORKSPACE 1)
    print("3. [WORKSPACE 2] Login (Kick 1)...")
    r3 = requests.post(f"{BASE_URL}/login?device_category=WORKSPACE", data={"username": "testuser", "password": "password123"})
    token_pc2 = r3.json().get("access_token")

    print("\n--- Validation ---\n")

    # A: MOBILE should be alive
    res_a = requests.get(f"{BASE_URL}/list", headers={"Authorization": f"Bearer {token_mobile}"})
    print(f"Result A (MOBILE): {res_a.status_code}")

    # B: WORKSPACE 1 should be KICKED
    res_b = requests.get(f"{BASE_URL}/list", headers={"Authorization": f"Bearer {token_pc1}"})
    print(f"Result B (PC 1 - Kicked): {res_b.status_code}")
    if res_b.status_code == 401:
        print(f"Message: {res_b.json().get('detail')}")

    # C: WORKSPACE 2 should be alive
    res_c = requests.get(f"{BASE_URL}/list", headers={"Authorization": f"Bearer {token_pc2}"})
    print(f"Result C (PC 2): {res_c.status_code}")

if __name__ == "__main__":
    test_session_logic()
