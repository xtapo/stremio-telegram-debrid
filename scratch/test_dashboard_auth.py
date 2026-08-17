import sys, os
sys.path.insert(0, os.path.abspath("."))
from fastapi.testclient import TestClient
from addon import app
from config import Config

client = TestClient(app)

def test_auth_flow():
    print("1. Testing login page when auth is not set...")
    res = client.get("/login")
    print("Login page status:", res.status_code)
    # When no password set, /login redirects to /dashboard or renders login
    assert res.status_code in [200, 302]

    print("2. Setting a DASHBOARD_PASSWORD...")
    Config.DASHBOARD_PASSWORD = "mypassword123"
    Config.DASHBOARD_USERNAME = "admin"

    print("3. Testing /dashboard access without cookie (should redirect 302 to /login)...")
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers.get("location", "")
    print(" - Redirected properly to:", res.headers.get("location"))

    print("4. Testing invalid login...")
    res = client.post("/api/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert res.status_code == 401
    assert res.json()["success"] is False
    print(" - Rejected invalid password as expected")

    print("5. Testing valid login...")
    res = client.post("/api/auth/login", json={"username": "admin", "password": "mypassword123"})
    assert res.status_code == 200
    assert res.json()["success"] is True
    assert "dashboard_session" in res.cookies
    session_cookie = res.cookies["dashboard_session"]
    print(" - Received valid session cookie:", session_cookie[:25] + "...")

    print("6. Testing /dashboard with authenticated cookie...")
    client.cookies.set("dashboard_session", session_cookie)
    res = client.get("/dashboard", follow_redirects=False)
    assert res.status_code == 200
    assert "Addon Studio" in res.text
    print(" - Authenticated access to /dashboard granted successfully!")

    print("7. Testing /logout...")
    res = client.get("/logout", follow_redirects=False)
    assert res.status_code == 302
    assert "/login" in res.headers.get("location", "")
    print(" - Logged out and redirected to /login")

    print("8. Resetting password for dev...")
    Config.DASHBOARD_PASSWORD = ""
    print("All Auth tests passed successfully!")

if __name__ == "__main__":
    test_auth_flow()
