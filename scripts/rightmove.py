# /// script
# requires-python = ">=3.12"
# dependencies = [
#    "requests",
#    "beautifulsoup4",
#    "loguru",
#    "python-dotenv",
# ]
# ///
import csv
import json
import os
import time
import requests
from bs4 import BeautifulSoup
from loguru import logger
from dotenv import load_dotenv
import smtplib
from email.mime.text import MIMEText

load_dotenv()


GMAIL_USER = os.environ.get("GMAIL_USER")        # your.email@gmail.com
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
NOTIFY_EMAILS = os.environ.get("NOTIFY_EMAILS", "").split(",")  # comma-separated recipients


def on_new_property(prop_id: str, price: str, address: str, url: str) -> None:
    """Handle a newly discovered property. Extend this to add notifications, alerts, etc."""
    logger.info(f"[NEW PROPERTY] ID: {prop_id} - £{price} - {address}")

    send_email(
        subject=f"🏠 New property: £{price} — {address}",
        body=f"New property listed:\n\n£{price} — {address}\n{url}"
    )


def on_scrape_complete(current_records: dict, previous_records: dict) -> None:
    """Called when the scraper finishes. Summarises what was found."""
    total = len(current_records)
    new_count = sum(1 for pid in current_records if pid not in previous_records)
    price_changes = sum(
        1 for pid, info in current_records.items()
        if pid in previous_records and previous_records[pid]["price"] != info["price"]
    )

    if total == 0:
        logger.info("Scrape complete — no properties found.")
        return

    logger.info(f"Scrape complete — {total} properties tracked, {new_count} new, {price_changes} price changes.")


def send_email(subject: str, body: str) -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logger.warning("Gmail credentials not set, skipping notification")
        return
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(NOTIFY_EMAILS)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, NOTIFY_EMAILS, msg.as_string())
    except Exception:
        logger.exception("Failed to send email notification")


def load_previous_csv(filepath):
    """Read stored property data from disk with explicit safety delays."""
    time.sleep(1)
    records = {}
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                records[row["id"]] = {
                    "price": row["price"],
                    "address": row["address"],
                    "url": row["url"],
                }
    return records


def save_current_csv(filepath, data):
    """Write updated property data to disk with explicit safety delays."""
    time.sleep(3)
    fieldnames = ["id", "price", "address", "url"]
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for prop_id, info in data.items():
            writer.writerow(
                {
                    "id": prop_id,
                    "price": info["price"],
                    "address": info["address"],
                    "url": info["url"],
                }
            )


def monitor_rightmove():
    """Fetch property updates across all pages and highlight adjustments."""
    url = "https://www.rightmove.co.uk/property-for-sale/find.html"
    base_params = {
        "searchLocation": "Horsham, West Sussex",
        "useLocationIdentifier": "true",
        "locationIdentifier": "REGION^660",
        "minBedrooms": "2",
        "minPrice": "350000",
        "maxPrice": "400000",
        "radius": "0.0",
        "_includeSSTC": "on",
        "dontShow": "newHome,retirement,sharedOwnership,auction",
        "sortType": "2",
        "channel": "BUY",
        "transactionType": "BUY",
        "displayLocationIdentifier": "Horsham.html",
        "numberOfPropertiesPerPage": "24",
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    }

    data_dir = os.path.expanduser("~/data")
    os.makedirs(data_dir, exist_ok=True)
    db_file = os.path.join(data_dir, "tracked_properties.csv")

    previous_records = load_previous_csv(db_file)
    current_records = {}

    current_page = 1
    has_more_pages = True

    while has_more_pages:
        params = base_params.copy()
        if current_page > 1:
            params["index"] = str((current_page - 1) * 24)

        response = requests.get(url, params=params, headers=headers)
        if response.status_code != 200:
            logger.error(f"Request failed with status {response.status_code} on page {current_page}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if not script_tag or not script_tag.string:
            logger.warning(f"No __NEXT_DATA__ script tag found on page {current_page}")
            break

        try:
            payload = json.loads(script_tag.string)
            search_results = (
                payload.get("props", {})
                .get("pageProps", {})
                .get("searchResults", {})
            )
            properties = search_results.get("properties", [])
            pagination = search_results.get("pagination", {})
        except json.JSONDecodeError:
            logger.exception("Failed to parse __NEXT_DATA__ JSON")
            break

        if not properties:
            logger.debug(f"No properties found on page {current_page}, stopping pagination")
            break

        for prop in properties:
            prop_id = str(prop.get("id"))
            if not prop_id or prop_id in current_records:
                continue

            price = str(prop.get("price", {}).get("amount", ""))
            address = prop.get("displayAddress", "")
            url_path = f"https://www.rightmove.co.uk{prop.get('propertyUrl', '')}"

            current_records[prop_id] = {
                "price": price,
                "address": address,
                "url": url_path,
            }

            if prop_id not in previous_records:
                on_new_property(prop_id, price, address, url_path)
            elif previous_records[prop_id]["price"] != price:
                old_price = previous_records[prop_id]["price"]
                logger.info(f"[PRICE CHANGE] ID: {prop_id} - £{old_price} → £{price} - {address}")

        total_pages_str = pagination.get("total")
        try:
            total_pages = int(total_pages_str) if total_pages_str else 1
        except ValueError:
            total_pages = 1

        logger.debug(f"Processed page {current_page}/{total_pages}")

        if current_page < total_pages:
            current_page += 1
            time.sleep(1)
        else:
            has_more_pages = False

    save_current_csv(db_file, current_records)
    on_scrape_complete(current_records, previous_records)


if __name__ == "__main__":
    monitor_rightmove()