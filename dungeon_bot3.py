import requests
import time
import random
import json
import re
from dotenv import load_dotenv
import os

# === CONFIGURATION ===
load_dotenv(dotenv_path='dungeon_bot2.env')
USER_TOKEN = os.getenv('USER_TOKEN')
DUNGEON_CHANNEL_ID = '1091695385183010887'
GUILD_ID = '1089832785872699473'
PING_USER_ID = '660460983382441984'
APPLICATION_ID = '706183309943767112'
COMMAND_ID = '1014616988993204284'
COMMAND_VERSION = '1087099255652622437'
WEBHOOK_CHANNEL_ID = '1407808332034605137'
WEBHOOK_URL = 'https://discordapp.com/api/webhooks/1407923565327552552/S3MPtc9RVGqo8pemRVWqWFvjzgZDIDxDYeAHKEwxj_4_L7oisZdUG1ZY1hWFC_R7mEPl'

HEADERS = {
    "Authorization": USER_TOKEN,
    "Content-Type": "application/json"
}

# Reuse connections
SESSION = requests.Session()

# === VARIABLES ===
running = True
paused = False
dungeon_active = False
current_run = 0
max_runs = random.randint(450, 550)
base_time_per_run = random.uniform(3.8, 4.0)
buffer_time = 240
total_run_time = base_time_per_run * max_runs
start_time = None
last_run_time = None
estimated_fixed_time = 3.5
mood = 'fast'
processed_message_ids = set()
command_timestamps = []
captcha_start_time = None
last_captcha_solved_id = None

# === LOGGING ===
def log(message):
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - {message}")

# === TOKEN VALIDATION ===
def validate_token():
    if not USER_TOKEN:
        log("Error: USER_TOKEN not found in dungeon_bot2.env. Please set a valid token.")
        return False
    try:
        response = SESSION.get("https://discord.com/api/v10/users/@me", headers=HEADERS, timeout=5.0)
        if response.status_code == 200:
            log("USER_TOKEN validated successfully.")
            return True
        else:
            log(f"Error: Invalid USER_TOKEN (Status: {response.status_code}, Response: {response.text}). Please update dungeon_bot2.env.")
            return False
    except requests.exceptions.RequestException as e:
        log(f"Error validating USER_TOKEN: {e}")
        return False

# === WEBHOOK WITH RETRY ===
def send_webhook_with_retry(payload, max_retries=3):
    for attempt in range(max_retries):
        try:
            response = SESSION.post(WEBHOOK_URL, json=payload, timeout=5.0)
            if response.status_code in (200, 204):
                log("Webhook notification sent successfully.")
                return True
            else:
                log(f"Failed to send webhook notification (Status: {response.status_code}, Response: {response.text})")
                time.sleep(2 ** attempt)
                continue
        except requests.exceptions.RequestException as e:
            log(f"Webhook error (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(2 ** attempt)
            continue
    log("Max retries reached for webhook, giving up.")
    return False

# === STARTUP ===
if not validate_token():
    log("Bot cannot start due to invalid USER_TOKEN. Exiting.")
    exit(1)

log("Bot started and running. Waiting for !start command in webhook channel.")
webhook_payload = {"content": f"<@{PING_USER_ID}> Bot started and running. Send !start to begin dungeon runs in <#{WEBHOOK_CHANNEL_ID}>."}
send_webhook_with_retry(webhook_payload)

# === FUNCTIONS ===
def make_payload():
    return {
        "type": 2,
        "application_id": APPLICATION_ID,
        "guild_id": GUILD_ID,
        "channel_id": DUNGEON_CHANNEL_ID,
        "session_id": "dummy_session",
        "data": {
            "id": COMMAND_ID,
            "name": "dungeon",
            "version": COMMAND_VERSION,
            "type": 1,
            "options": [
                {"name": "floor", "type": 4, "value": 30},
                {"name": "difficulty", "type": 3, "value": "1"}
            ]
        },
        "nonce": str(int(time.time() * 1000)) + str(random.randint(1000, 9999))
    }

def send_dungeon_command():
    global command_timestamps
    if not running or paused or not dungeon_active:
        return False
    current_time = time.time()
    command_timestamps = [t for t in command_timestamps if current_time - t < 7]
    if len(command_timestamps) >= 3:
        wait_time = 7 - (current_time - command_timestamps[0])
        if wait_time > 0:
            log(f"Hit 3/7s command limit, waiting {wait_time:.2f}s")
            time.sleep(wait_time)
    payload = make_payload()
    url = "https://discord.com/api/v10/interactions"
    max_retries = 3
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(0.7, 0.9))
            start_api = time.time()
            response = SESSION.post(url, headers=HEADERS, data=json.dumps(payload), timeout=3.0)
            api_time = time.time() - start_api
            command_timestamps.append(time.time())
            limit = response.headers.get('X-RateLimit-Limit', 'Unknown')
            remaining = response.headers.get('X-RateLimit-Remaining', 'Unknown')
            reset = response.headers.get('X-RateLimit-Reset-After', 'Unknown')
            log(f"Status: {response.status_code}, Response: {response.text}, API time: {api_time:.2f}s, Rate Limit: {limit}, Remaining: {remaining}, Reset After: {reset}s")
            if response.status_code == 429:
                retry_after = float(response.json().get('retry_after', 5.0))
                log(f"Hit rate limit, retrying after {retry_after:.2f}s...")
                time.sleep(retry_after + random.uniform(0.1, 0.3))
                continue
            elif response.status_code != 204:
                log("Non-204 response, stopping the dungeon runs.")
                return False
            return True
        except requests.exceptions.RequestException as e:
            log(f"Network error (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(2 ** attempt)
            continue
    log("Max retries reached, stopping.")
    return False

def check_for_captcha_message():
    global processed_message_ids
    try:
        response = SESSION.get(
            f"https://discord.com/api/v10/channels/{DUNGEON_CHANNEL_ID}/messages?limit=4",
            headers=HEADERS,
            timeout=3.0
        )
        if response.status_code == 200:
            messages = response.json()
            for message in messages:
                message_id = message['id']
                if message_id in processed_message_ids:
                    continue
                content = message.get('content', '')
                for keyword in [
                    "use /captcha to enter the code",
                    "please use /captcha",
                    "enter the code with /captcha",
                    "captcha required",
                    "verify with /captcha",
                    "/captcha",
                    "captcha"
                ]:
                    if keyword in content.lower():
                        log(f"Captcha keyword detected in message ID {message_id}: '{keyword}'")
                        processed_message_ids.add(message_id)
                        return True
                processed_message_ids.add(message_id)
            return False
        else:
            log(f"Error fetching messages: {response.status_code}, {response.text}")
            return False
    except Exception as e:
        log(f"Network error fetching messages: {e}")
        return False

def handle_captcha():
    global paused, captcha_start_time
    if not paused:
        paused = True
        captcha_start_time = time.time()
        log("Captcha detected, dungeon runs paused.")
        webhook_payload = {"content": f"<@{PING_USER_ID}> Captcha detected! Pausing dungeon runs. Please resolve the captcha in <#{DUNGEON_CHANNEL_ID}>."}
        send_webhook_with_retry(webhook_payload)

def check_captcha_solved():
    global paused, captcha_start_time, processed_message_ids, last_captcha_solved_id
    try:
        response = SESSION.get(
            f"https://discord.com/api/v10/channels/{DUNGEON_CHANNEL_ID}/messages?limit=1",
            headers=HEADERS,
            timeout=3.0
        )
        if response.status_code == 200:
            messages = response.json()
            if not messages:
                return False
            message = messages[0]
            message_id = message['id']
            if message_id in processed_message_ids or message_id == last_captcha_solved_id:
                return False
            content = message.get('content', '')
            if content.lower() == "thank you!":
                log(f"Captcha solved confirmed: 'Thank you!' in message ID {message_id}.")
                processed_message_ids.add(message_id)
                last_captcha_solved_id = message_id
                paused = False
                captcha_start_time = None
                webhook_payload = {"content": f"<@{PING_USER_ID}> Captcha solved! Resuming dungeon runs."}
                send_webhook_with_retry(webhook_payload)
                return True
            processed_message_ids.add(message_id)
            return False
        else:
            log(f"Error fetching messages: {response.status_code}, {response.text}")
            return False
    except Exception as e:
        log(f"Network error fetching messages: {e}")
        return False

def check_control_commands():
    global dungeon_active, current_run, max_runs, base_time_per_run, total_run_time, start_time, last_run_time, mood, processed_message_ids
    max_retries = 5
    for attempt in range(max_retries):
        try:
            url = f"https://discord.com/api/v10/channels/{WEBHOOK_CHANNEL_ID}/messages?limit=1"
            response = SESSION.get(url, headers=HEADERS, timeout=3.0)
            if response.status_code == 200:
                messages = response.json()
                if messages:
                    message = messages[0]
                    message_id = message.get('id', 'Unknown')
                    if message_id in processed_message_ids:
                        return False
                    if message.get('author', {}).get('id') == PING_USER_ID:
                        content = message.get('content', '').lower()
                        if content == '!start' and not dungeon_active:
                            processed_message_ids.clear()
                            processed_message_ids.add(message_id)
                            dungeon_active = True
                            current_run = 0
                            max_runs = random.randint(450, 550)
                            base_time_per_run = random.uniform(3.8, 4.0)
                            total_run_time = base_time_per_run * max_runs
                            start_time = None
                            last_run_time = None
                            mood = 'fast'
                            log(f"Received !start command (Message ID: {message_id}). Starting dungeon runs.")
                            webhook_payload = {
                                "content": f"<@{PING_USER_ID}> Started dungeon runs: {max_runs} runs, "
                                           f"estimated {int(total_run_time // 60)}m {int(total_run_time % 60)}s "
                                           f"(up to {int((total_run_time + buffer_time) // 60)}m {int((total_run_time + buffer_time) % 60)}s with buffer)."
                            }
                            send_webhook_with_retry(webhook_payload)
                            return True
                        elif content == '!stop' and dungeon_active:
                            processed_message_ids.add(message_id)
                            dungeon_active = False
                            log(f"Received !stop command (Message ID: {message_id}). Stopping dungeon runs.")
                            webhook_payload = {"content": f"<@{PING_USER_ID}> Dungeon runs stopped at {current_run}/{max_runs} runs."}
                            send_webhook_with_retry(webhook_payload)
                            return True
                return False
            else:
                log(f"Failed to fetch latest message for control commands: {response.status_code} {response.text}")
                time.sleep(2 ** attempt)
                continue
        except requests.exceptions.RequestException as e:
            log(f"Network error checking control commands (attempt {attempt + 1}/{max_retries}): {e}")
            time.sleep(2 ** attempt)
            continue
    log("Max retries reached for control commands, continuing.")
    return False

def main_loop():
    global current_run, start_time, last_run_time, mood, running, dungeon_active
    try:
        while running:
            check_control_commands()
            if not dungeon_active:
                log("Waiting for !start command to begin new run cycle.")
                time.sleep(2)
                continue

            if not start_time:
                start_time = time.time()
                last_run_time = start_time
                log(f"Target runtime: {int(total_run_time // 60)}m {int(total_run_time % 60)}s "
                    f"(up to {int((total_run_time + buffer_time) // 60)}m {int((total_run_time + buffer_time) % 60)}s with 4min buffer) for {max_runs} runs "
                    f"(base time per run: {base_time_per_run:.2f}s)")

            # Add 0.2s delay to stabilize message fetch
            time.sleep(0.2)
            if check_for_captcha_message():
                handle_captcha()
                while paused and running and dungeon_active:
                    time.sleep(1.0)
                    if check_captcha_solved():
                        break
                continue

            if not send_dungeon_command():
                dungeon_active = False
                log("Dungeon command failed, stopping current run cycle.")
                webhook_payload = {"content": f"<@{PING_USER_ID}> Dungeon runs stopped due to command failure at {current_run}/{max_runs} runs."}
                send_webhook_with_retry(webhook_payload)
                continue

            time.sleep(random.uniform(0.6, 0.8))
            if check_for_captcha_message():  # Double-check post-command
                handle_captcha()
                while paused and running and dungeon_active:
                    time.sleep(1.0)
                    if check_captcha_solved():
                        break
                continue

            current_run += 1
            current_time = time.time()
            elapsed = current_time - start_time
            actual_run_time = current_time - last_run_time
            last_run_time = current_time
            remaining_runs = max_runs - current_run
            remaining_time = total_run_time - elapsed
            expected_time = current_run * base_time_per_run

            log(f"Run {current_run}/{max_runs} complete. Remaining runs: {remaining_runs}")
            log(f"Elapsed time: {int(elapsed // 60)}m {int(elapsed % 60)}s | "
                f"Remaining time approx: {int(remaining_time // 60)}m {int(remaining_time % 60)}s | "
                f"Last run took: {actual_run_time:.1f}s")

            if current_run % 100 == 0 and current_run > 0:
                webhook_payload = {"content": f"<@{PING_USER_ID}> Reached {current_run}/{max_runs} runs."}
                send_webhook_with_retry(webhook_payload)

            if remaining_runs > 0:
                if elapsed >= 30 * 60:
                    log("Approaching 30m, entering buffer mode to complete runs")
                    buffer_needed = min(remaining_runs * 3.8, 240)
                    log(f"Using {buffer_needed:.1f}s of buffer (capped at 240s)")
                    delay = random.uniform(0.6, 0.8)
                else:
                    target_delay = max(0.6, (remaining_time / remaining_runs) - 3.5)
                    is_behind = elapsed > expected_time + 50
                    if is_behind:
                        log("Behind schedule, forcing fast mode")
                        delay = random.uniform(max(0.6, min(target_delay, 0.8)), min(0.8, max(0.6, target_delay)))
                    else:
                        if mood == 'fast':
                            delay = random.uniform(max(0.6, min(target_delay, 0.8)), min(0.8, max(0.6, target_delay)))
                        else:
                            delay = random.uniform(max(0.8, min(target_delay, 1.0)), min(1.0, max(0.8, target_delay)))
            else:
                delay = random.uniform(0.6, 0.8)
            log(f"Sending next dungeon command after {delay:.1f} seconds")
            time.sleep(delay)

            if current_run >= max_runs:
                log(f"Run cycle complete. Completed {current_run}/{max_runs} runs in {int(elapsed // 60)}m {int(elapsed % 60)}s.")
                webhook_payload = {"content": f"<@{PING_USER_ID}> Dungeon runs done! Completed {current_run}/{max_runs} runs. Send !start for a new cycle."}
                send_webhook_with_retry(webhook_payload)
                dungeon_active = False
                processed_message_ids.clear()
                continue

    except KeyboardInterrupt:
        running = False
        dungeon_active = False
        log("Bot interrupted by user, stopping.")
        elapsed = time.time() - start_time if start_time else 0
        log(f"Bot has finished its run. Completed {current_run}/{max_runs} runs in {int(elapsed // 60)}m {int(elapsed % 60)}s.")
        webhook_payload = {"content": f"<@{PING_USER_ID}> Dungeon runs interrupted! Completed {current_run}/{max_runs} runs."}
        send_webhook_with_retry(webhook_payload)

if __name__ == "__main__":
    main_loop()