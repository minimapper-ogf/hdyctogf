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
USER_ID_START = 1
USER_ID_END = 30000

# Time range for "last 30 days"
TODAY = datetime.utcnow()
LAST_30_DAYS = TODAY - timedelta(days=30)

# Limit concurrent requests to avoid overloading the API
CONCURRENT_REQUESTS = 100

# Fetch changesets for a given user
async def fetch_changesets(session, user_id, last_changeset_id):
    url = f"https://opengeofiction.net/api/0.6/changesets?user={user_id}"
    try:
        async with session.get(url, timeout=10) as response:
            if response.status != 200:
                return None  # User has no changesets or API issue
            xml_text = await response.text()
            changesets = ET.fromstring(xml_text).findall("changeset")
            
            # Filter out changesets already processed
            new_changesets = [cs for cs in changesets if int(cs.get("id")) > last_changeset_id]
            return new_changesets
    except Exception:
        return None  # Handle request failures

# Process and extract user stats
async def process_user(session, user_id):
    existing_data = load_existing_data(user_id)
    last_changeset_id = existing_data.get("last_changeset_id", 0) if existing_data else 0
    
    changesets = await fetch_changesets(session, user_id, last_changeset_id)
    if not changesets:
        print(f"Skipping user {user_id}, no new changesets found.")
        return None  # No new edits found

    edit_days = set()
    total_changes = existing_data.get("total_changes", 0)
    last_30_days_changes = existing_data.get("last_30_days_changes", 0)
    active_edit_days_30 = set(existing_data.get("active_edit_days_30", []))
    editor_usage = defaultdict(int, existing_data.get("editor_usage", {}))
    source_usage = defaultdict(int, existing_data.get("source_usage", {}))
    weekday_edits = defaultdict(int, existing_data.get("weekday_edits", {}))
    hourly_edits = defaultdict(int, existing_data.get("hourly_edits", {}))
    changeset_count = existing_data.get("changeset_count", 0)
    changesets_with_comments = existing_data.get("changesets_with_comments", 0)
    username = existing_data.get("username", None)
    
    for cs in changesets:
        cs_id = int(cs.get("id"))
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

    new_data = {
        "user_id": user_id,
        "username": username,
        "first_edit": existing_data.get("first_edit", min(edit_days)),
        "last_edit": max(edit_days),
        "total_edit_days": len(edit_days | set(existing_data.get("edit_days", []))),
        "active_edit_days_30": len(active_edit_days_30),
        "total_changes": total_changes,
        "last_30_days_changes": last_30_days_changes,
        "most_used_editor": max(editor_usage, key=editor_usage.get, default="Unknown"),
        "most_used_source": max(source_usage, key=source_usage.get, default="Unknown"),
        "changeset_count": changeset_count,
        "changesets_with_comments": changesets_with_comments,
        "weekday_edits": dict(weekday_edits),
        "hourly_edits": dict(hourly_edits),
        "last_changeset_id": max(int(cs.get("id")) for cs in changesets),
    }
    print(f"Processed user {user_id}: {username}")
    save_to_csv(new_data)

# Load existing data from CSV
def load_existing_data(user_id):
    file_path = os.path.join(DATA_FOLDER, f"{user_id}.csv")
    if not os.path.exists(file_path):
        return None
    
    with open(file_path, "r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            return {k: eval(v) if v.startswith("{") else v for k, v in row.items()}
    return None

# Save user stats to a CSV file
def save_to_csv(user_stats):
    file_path = os.path.join(DATA_FOLDER, f"{user_stats['user_id']}.csv")
    with open(file_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(user_stats.keys())
        writer.writerow(user_stats.values())
    print(f"? Saved stats for {user_stats['username']} (User {user_stats['user_id']})")

# Process users in batches
async def process_users_in_batches():
    async with aiohttp.ClientSession() as session:
        tasks = []
        for user_id in range(USER_ID_START, USER_ID_END + 1):
            tasks.append(process_user(session, user_id))
            if len(tasks) >= CONCURRENT_REQUESTS:  # Process in batches
                results = await asyncio.gather(*tasks)
                tasks = []  # Reset batch
        
        if tasks:
            await asyncio.gather(*tasks)

# Run script
if __name__ == "__main__":
    asyncio.run(process_users_in_batches())