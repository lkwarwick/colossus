#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "feedparser",
#     "python-dateutil",
#     "loguru",
#     "python-dotenv",
# ]
# ///
"""
Scrape the Databricks release notes RSS feed and email a styled summary of
everything published in the last 24 hours *from the moment the script runs*.

Feed source:
    https://docs.databricks.com/aws/en/feed.xml

Because the cutoff is always "now - 24h" (not "midnight" or "yesterday"),
running this once a day on a schedule will not re-emit items you've already
seen, as long as it runs on a roughly 24h cadence.

Env vars (.env or environment):
    GMAIL_USER            your.email@gmail.com
    GMAIL_APP_PASSWORD    Gmail app password (not your normal password)
    NOTIFY_EMAILS         comma-separated recipient list

Usage:
    ./databricks_release_notes_scraper.py
    ./databricks_release_notes_scraper.py --hours 24
    ./databricks_release_notes_scraper.py --feed-url https://docs.databricks.com/gcp/en/feed.xml
    ./databricks_release_notes_scraper.py --dry-run   # print email instead of sending
"""

from __future__ import annotations

import argparse
import html
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import feedparser
from dateutil import parser as dateutil_parser
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

DEFAULT_FEED_URL = "https://docs.databricks.com/aws/en/feed.xml"

GMAIL_USER = os.environ.get("GMAIL_USER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
NOTIFY_EMAILS = [e.strip() for e in os.environ.get("NOTIFY_EMAILS", "").split(",") if e.strip()]


@dataclass
class Article:
    title: str
    link: str
    published: datetime  # tz-aware UTC
    summary: str


# --------------------------------------------------------------------------
# Scraping
# --------------------------------------------------------------------------

def parse_entry_date(entry) -> datetime | None:
    """Return a timezone-aware UTC datetime for a feedparser entry, or None."""
    for attr in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, attr, None)
        if struct:
            return datetime(*struct[:6], tzinfo=timezone.utc)

    for attr in ("published", "updated"):
        raw = getattr(entry, attr, None)
        if raw:
            try:
                dt = dateutil_parser.parse(raw)
            except (ValueError, TypeError):
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)

    return None


def fetch_recent_articles(feed_url: str, hours: int = 24) -> list[Article]:
    logger.info(f"Fetching feed: {feed_url}")
    feed = feedparser.parse(feed_url)

    if feed.bozo and not feed.entries:
        raise RuntimeError(f"Failed to parse feed at {feed_url}: {feed.bozo_exception}")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=hours)

    recent: list[Article] = []
    for entry in feed.entries:
        published_dt = parse_entry_date(entry)
        if published_dt is None:
            continue
        if published_dt >= cutoff:
            recent.append(
                Article(
                    title=getattr(entry, "title", "").strip(),
                    link=getattr(entry, "link", "").strip(),
                    published=published_dt,
                    summary=getattr(entry, "summary", "").strip(),
                )
            )

    recent.sort(key=lambda a: a.published, reverse=True)
    logger.info(f"Found {len(recent)} article(s) in the last {hours}h (of {len(feed.entries)} total in feed).")
    return recent


# --------------------------------------------------------------------------
# Email rendering
# --------------------------------------------------------------------------

def build_html_email(articles: list[Article], hours: int, feed_url: str) -> str:
    now = datetime.now(timezone.utc)
    total = len(articles)

    metrics_html = f"""
      <tr>
        <td style="padding:0 12px 0 0;">
          <div style="background:#f4f6f8;border-radius:10px;padding:16px 20px;text-align:center;min-width:120px;">
            <div style="font-size:28px;font-weight:700;color:#FF3621;">{total}</div>
            <div style="font-size:12px;color:#5f6b7a;text-transform:uppercase;letter-spacing:.04em;">New articles</div>
          </div>
        </td>
        <td style="padding:0 12px;">
          <div style="background:#f4f6f8;border-radius:10px;padding:16px 20px;text-align:center;min-width:120px;">
            <div style="font-size:28px;font-weight:700;color:#1B3139;">{hours}h</div>
            <div style="font-size:12px;color:#5f6b7a;text-transform:uppercase;letter-spacing:.04em;">Look-back window</div>
          </div>
        </td>
        <td style="padding:0 0 0 12px;">
          <div style="background:#f4f6f8;border-radius:10px;padding:16px 20px;text-align:center;min-width:120px;">
            <div style="font-size:14px;font-weight:700;color:#1B3139;padding-top:6px;">{now.strftime('%d %b, %H:%M UTC')}</div>
            <div style="font-size:12px;color:#5f6b7a;text-transform:uppercase;letter-spacing:.04em;">Run time</div>
          </div>
        </td>
      </tr>
    """

    if total == 0:
        body_html = """
          <tr><td style="padding:28px 32px;color:#5f6b7a;font-size:14px;">
            No Databricks release notes were published in this window. Nothing to report today.
          </td></tr>
        """
    else:
        cards = []
        for a in articles:
            title = html.escape(a.title)
            link = html.escape(a.link)
            summary = html.escape(a.summary) if a.summary else ""
            when = a.published.strftime("%d %b %Y, %H:%M UTC")
            cards.append(f"""
              <tr>
                <td style="padding:0 32px 20px 32px;">
                  <div style="border:1px solid #e6e9ec;border-left:4px solid #FF3621;border-radius:8px;padding:16px 20px;">
                    <div style="font-size:11px;color:#8a97a3;text-transform:uppercase;letter-spacing:.04em;margin-bottom:6px;">{when}</div>
                    <a href="{link}" style="font-size:16px;font-weight:600;color:#1B3139;text-decoration:none;">{title}</a>
                    {f'<div style="font-size:14px;color:#4a5560;margin-top:8px;line-height:1.5;">{summary}</div>' if summary else ''}
                    <div style="margin-top:10px;">
                      <a href="{link}" style="font-size:13px;color:#FF3621;font-weight:600;text-decoration:none;">Read more &rarr;</a>
                    </div>
                  </div>
                </td>
              </tr>
            """)
        body_html = "".join(cards)

    return f"""\
<!DOCTYPE html>
<html>
  <body style="margin:0;padding:0;background:#eef1f3;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef1f3;padding:24px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:12px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.06);">
            <tr>
              <td style="background:#1B3139;padding:24px 32px;">
                <div style="font-size:20px;font-weight:700;color:#ffffff;">Databricks Release Notes</div>
                <div style="font-size:13px;color:#b7c2c9;margin-top:4px;">Daily digest &middot; <a href="{html.escape(feed_url)}" style="color:#b7c2c9;">{html.escape(feed_url)}</a></div>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 32px 8px 32px;">
                <table role="presentation" cellpadding="0" cellspacing="0">
                  {metrics_html}
                </table>
              </td>
            </tr>
            <tr><td style="padding:8px 32px;"><hr style="border:none;border-top:1px solid #e6e9ec;"></td></tr>
            {body_html}
            <tr>
              <td style="padding:20px 32px;background:#f9fafb;">
                <div style="font-size:12px;color:#9aa5ad;">
                  Automated digest generated at {now.strftime('%Y-%m-%d %H:%M UTC')}. Cutoff is a rolling {hours}-hour window from run time, so daily runs won't duplicate items.
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>
"""


def build_plaintext_email(articles: list[Article], hours: int, feed_url: str) -> str:
    now = datetime.now(timezone.utc)
    lines = [
        "Databricks Release Notes — Daily Digest",
        f"Feed: {feed_url}",
        f"Run time: {now.strftime('%Y-%m-%d %H:%M UTC')}",
        f"New articles: {len(articles)} (last {hours}h)",
        "",
    ]
    if not articles:
        lines.append("No new release notes in this window.")
    else:
        for a in articles:
            lines.append(f"- [{a.published.strftime('%Y-%m-%d %H:%M UTC')}] {a.title}")
            lines.append(f"  {a.link}")
            if a.summary:
                lines.append(f"  {a.summary}")
            lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Email sending
# --------------------------------------------------------------------------

def send_email(subject: str, html_body: str, text_body: str) -> None:
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        logger.warning("Gmail credentials not set, skipping notification")
        return
    if not NOTIFY_EMAILS:
        logger.warning("No NOTIFY_EMAILS configured, skipping notification")
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = ", ".join(NOTIFY_EMAILS)
    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            smtp.sendmail(GMAIL_USER, NOTIFY_EMAILS, msg.as_string())
        logger.info(f"Email sent to {', '.join(NOTIFY_EMAILS)}")
    except Exception:
        logger.exception("Failed to send email notification")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed-url", default=DEFAULT_FEED_URL, help=f"RSS feed URL (default: {DEFAULT_FEED_URL})")
    parser.add_argument("--hours", type=int, default=24, help="Look-back window in hours from run time (default: 24)")
    parser.add_argument("--dry-run", action="store_true", help="Print the email instead of sending it")
    parser.add_argument(
        "--send-if-empty",
        action="store_true",
        help="Send an email even when there are zero new articles (default: skip sending)",
    )
    args = parser.parse_args()

    articles = fetch_recent_articles(args.feed_url, hours=args.hours)

    subject = (
        f"🧱 Databricks Release Notes: {len(articles)} update(s) in the last {args.hours}h"
        if articles
        else f"🧱 Databricks Release Notes: no updates in the last {args.hours}h"
    )
    html_body = build_html_email(articles, args.hours, args.feed_url)
    text_body = build_plaintext_email(articles, args.hours, args.feed_url)

    if args.dry_run:
        print(text_body)
        return

    if not articles and not args.send_if_empty:
        logger.info("No new articles and --send-if-empty not set; skipping email.")
        return

    send_email(subject=subject, html_body=html_body, text_body=text_body)


if __name__ == "__main__":
    main()