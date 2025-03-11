import os
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import csv
from datetime import datetime, timedelta
from collections import defaultdict

# Define storage folder
DATA_FOLDER = "data"
os.makedirs(DATA_FOLDER, exist_ok=True)

# Define range of user IDs to check
USER_ID_START = 3000
USER_ID_END = 30000

# Time range for "last 30 days"
TODAY = datetime.utcnow()
LAST_30_DAYS = TODAY - timedelta(days=30)

# Limit concurrent requests to avoid overloading the API
CONCURRENT_REQUESTS = 100

# Fetch changesets for a given user
async def fetch_changesets(session, user_id):
    url = f"https://opengeofiction.net/api/0.6/changesets?user={user_id}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                return None  # User has no changesets or API issue
            xml_text = await response.text()
            return ET.fromstring(xml_text).findall("changeset")
    except Exception:
        return None  # Handle request failures

# Process and extract user stats
async def process_user(session, user_id):
    changesets = await fetch_changesets(session, user_id)
    if not changesets:
        return None  # No edits found

    edit_days = set()
    total_changes = 0
    last_30_days_changes = 0
    active_edit_days_30 = set()
    editor_usage = defaultdict(int)
    source_usage = defaultdict(int)
    weekday_edits = defaultdict(int)
    hourly_edits = defaultdict(int)
    changeset_count = 0
    changesets_with_comments = 0
    username = None

    for cs in changesets:
        created_at = datetime.strptime(cs.get("created_at"), "%Y-%m-%dT%H:%M:%SZ")
        changes_count = int(cs.get("changes_count", 0))
        user_name = cs.get("user")
        comments_count = int(cs.get("comments_count", 0))

        if username is None:
            username = user_name  # Store username

        edit_days.add(created_at.date())
        total_changes += changes_count
        changeset_count += 1
        weekday_edits[created_at.weekday()] += 1  # 0 = Monday, 6 = Sunday
        hourly_edits[created_at.hour] += 1  # 0-23 UTC hours

        if comments_count > 0:
            changesets_with_comments += 1

        if created_at >= LAST_30_DAYS:
            last_30_days_changes += changes_count
            active_edit_days_30.add(created_at.date())

        # Extract editor and source usage
        for tag in cs.findall("tag"):
            key = tag.get("k")
            value = tag.get("v")
            if key == "created_by":
                editor_usage[value] += 1
            elif key == "source":
                source_usage[value] += 1

    return {
        "user_id": user_id,
        "username": username,
        "first_edit": min(edit_days),
        "last_edit": max(edit_days),
        "total_edit_days": len(edit_days),
        "active_edit_days_30": len(active_edit_days_30),
        "total_changes": total_changes,
        "last_30_days_changes": last_30_days_changes,
        "most_used_editor": max(editor_usage, key=editor_usage.get, default="Unknown"),
        "most_used_source": max(source_usage, key=source_usage.get, default="Unknown"),
        "changeset_count": changeset_count,
        "changesets_with_comments": changesets_with_comments,
        "weekday_edits": dict(weekday_edits),  # Store as dictionary for later use
        "hourly_edits": dict(hourly_edits),  # Store as dictionary for later use
    }

# Save user stats to a CSV file
def save_to_csv(user_stats):
    file_path = os.path.join(DATA_FOLDER, f"{user_stats['user_id']}.csv")
    with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["User ID", "Username", "First Edit", "Last Edit", "Total Edit Days",
                         "Active Edit Days (Last 30 Days)", "Total Changes", "Changes (Last 30 Days)",
                         "Most Used Editor", "Most Used Source", "Total Changesets",
                         "Changesets with Comments", "Edits Per Weekday", "Edits Per Hour"])
        writer.writerow([
            user_stats["user_id"],
            user_stats["username"],
            user_stats["first_edit"],
            user_stats["last_edit"],
            user_stats["total_edit_days"],
            user_stats["active_edit_days_30"],
            user_stats["total_changes"],
            user_stats["last_30_days_changes"],
            user_stats["most_used_editor"],
            user_stats["most_used_source"],
            user_stats["changeset_count"],
            user_stats["changesets_with_comments"],
            str(user_stats["weekday_edits"]),  # Convert dict to string
            str(user_stats["hourly_edits"])  # Convert dict to string
        ])
    print(f"? Saved stats for {user_stats['username']} (User {user_stats['user_id']})")

# Process users in batches
async def process_users_in_batches():
    async with aiohttp.ClientSession() as session:
        tasks = []
        for user_id in range(USER_ID_START, USER_ID_END + 1):
            tasks.append(process_user(session, user_id))
            if len(tasks) >= CONCURRENT_REQUESTS:  # Process in batches of 100
                results = await asyncio.gather(*tasks)
                for user_stats in results:
                    if user_stats:
                        save_to_csv(user_stats)
                tasks = []  # Reset batch

        # Process remaining users in the last batch
        if tasks:
            results = await asyncio.gather(*tasks)
            for user_stats in results:
                if user_stats:
                    save_to_csv(user_stats)

# Run script
if __name__ == "__main__":
    asyncio.run(process_users_in_batches())
