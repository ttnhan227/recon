from __future__ import annotations

from pathlib import Path

from bs4 import BeautifulSoup


def test_demo_index_html_accessibility():
    index_path = (
        Path(__file__).parent.parent.parent / "recon" / "demo_app" / "static" / "index.html"
    )
    assert index_path.exists()
    content = index_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "html.parser")

    # 1. Landmarks
    assert soup.find("header", class_="app-header") is not None
    assert soup.find("main", id="main-content") is not None
    assert soup.find("footer", class_="app-footer") is not None

    # 2. Skip link
    skip_link = soup.find("a", class_="skip-link")
    assert skip_link is not None
    assert skip_link["href"] == "#main-content"

    # 3. Form input association
    for input_id in [
        "itemId",
        "quantity",
        "currency",
        "userName",
        "userEmail",
        "userPassword",
        "loginEmail",
        "loginPassword",
    ]:
        inp = soup.find("input", id=input_id)
        assert inp is not None, f"Input {input_id} not found"
        label = soup.find("label", attrs={"for": input_id})
        assert label is not None, f"Label for {input_id} not found"

    # 4. Autocomplete
    email_inp = soup.find("input", id="loginEmail")
    assert email_inp is not None
    assert email_inp.get("autocomplete") == "username"

    pwd_inp = soup.find("input", id="loginPassword")
    assert pwd_inp is not None
    assert pwd_inp.get("autocomplete") == "current-password"

    user_name_inp = soup.find("input", id="userName")
    assert user_name_inp is not None
    assert user_name_inp.get("autocomplete") == "name"

    # 5. Live regions for feedback
    order_result = soup.find("div", id="orderResult")
    assert order_result is not None
    assert order_result.get("role") == "status"
    assert order_result.get("aria-live") == "polite"

    login_result = soup.find("div", id="loginResult")
    assert login_result is not None
    assert login_result.get("role") == "alert"

    user_result = soup.find("div", id="userResult")
    assert user_result is not None
    assert user_result.get("role") == "status"

    # 6. Interactive trigger buttons
    assert soup.find("button", id="btnSlowAnalytics") is not None
    assert soup.find("button", id="btnInventoryLimit") is not None


def test_demo_dashboard_html_accessibility():
    dash_path = (
        Path(__file__).parent.parent.parent / "recon" / "demo_app" / "static" / "dashboard.html"
    )
    assert dash_path.exists()
    content = dash_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "html.parser")

    # 1. Landmarks
    assert soup.find("header", class_="dash-header") is not None
    assert soup.find("main", id="main-content") is not None
    assert soup.find("nav", class_="nav-actions") is not None
    assert soup.find("footer", class_="app-footer") is not None

    # 2. Table semantics
    table = soup.find("table")
    assert table is not None
    caption = table.find("caption")
    assert caption is not None
    headers = table.find_all("th")
    assert len(headers) >= 4
    for th in headers:
        assert th.get("scope") == "col"

    # 3. Search and live region
    order_search = soup.find("input", id="orderSearch")
    assert order_search is not None
    order_count_status = soup.find("div", id="orderCountStatus")
    assert order_count_status is not None
    assert order_count_status.get("aria-live") == "polite"

    # 4. Return link
    back_link = soup.find("a", class_="back-link")
    assert back_link is not None
    assert back_link["href"] == "/"
