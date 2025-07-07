from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv
from flask_cors import CORS
from user_agents import parse
import certifi
import os

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["http://localhost:4200", "https://ryanbeevers.github.io*", "http://raspberrypi.local:4200"])

try:
    client = MongoClient(
        os.environ.get("MONGO_URI"),
        tls=True,
        tlsCAFile=certifi.where()
    )
    client.server_info()
except ServerSelectionTimeoutError as err:
    print("Failed to connect to MongoDB:", err)
    exit(1)

db = client["resume_db"]
visits_col = db["visits"]
progress_col = db["progress"]

@app.route('/track-visit', methods=['POST'])
def track_visit():
    data = request.json

    forwarded_for = request.headers.get('X-Forwarded-For', request.remote_addr)
    ip_address = forwarded_for.split(',')[0].strip()
    ua_string = request.headers.get('User-Agent', '')
    user_agent = parse(ua_string)

    visit = {
        "user_id": data.get("user_id"),
        "username": data.get("username") or "anonymous",
        "ip_address": ip_address,
        "user_agent": request.headers.get('User-Agent'),
        "accept_language": request.headers.get('Accept-Language'),
        "referer": request.headers.get('Referer'),
        "platform": user_agent.os.family,
        "browser": user_agent.browser.family,
        "version": user_agent.browser.version_string,
        "mobile": user_agent.is_mobile,
        "timestamp": datetime.utcnow()
    }

    visits_col.insert_one(visit)
    return jsonify({"status": "visit logged"})

all_star_ids = {"star1", "star2", "star3", "star4", "star5"}

@app.route('/progress/star', methods=['POST'])
def add_star():
    data = request.json
    user_id = data.get("user_id")
    star_id = data.get("star_id")

    if not user_id or not star_id:
        return jsonify({"error": "Missing user_id or star_id"}), 400

    progress = progress_col.find_one({"user_id": user_id}) or {"stars_found": []}
    updated_stars = set(progress.get("stars_found", []))
    updated_stars.add(star_id)

    update_data = {
        "$addToSet": {"stars_found": star_id},
        "$set": {"last_updated": datetime.utcnow()}
    }

    if updated_stars == all_star_ids and not progress.get("completed"):
        update_data["$set"].update({
            "completed": True,
            "completed_at": datetime.utcnow()
        })

    result = progress_col.update_one(
        {"user_id": user_id},
        update_data,
        upsert=True
    )

    return jsonify({
        "status": "star added",
        "modified_count": result.modified_count,
        "completed": updated_stars == all_star_ids
    })


@app.route('/progress/<user_id>', methods=['GET'])
def get_progress(user_id):
    progress = progress_col.find_one({"user_id": user_id}, {"_id": 0})
    if not progress:
        return jsonify({"stars_found": []})
    return jsonify(progress)

@app.route('/progress/status/<user_id>', methods=['GET'])
def progress_status(user_id):
    progress = progress_col.find_one({"user_id": user_id}, {"_id": 0, "completed": 1})
    return jsonify({"completed": progress.get("completed", False)})

@app.route('/progress/complete', methods=['POST'])
def mark_complete():
    data = request.json
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"error": "Missing user_id"}), 400

    result = progress_col.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "completed": True,
                "completed_at": datetime.utcnow()
            }
        },
        upsert=True
    )
    return jsonify({"status": "completed", "modified_count": result.modified_count})
@app.route('/user-summary', methods=['GET'])
def get_user_summary():
    pipeline = [
        {"$sort": {"timestamp": -1}},  # Ensures latest values appear first
        {
            "$group": {
                "_id": "$user_id",
                "visit_count": {"$sum": 1},
                "last_visit": {"$first": "$timestamp"},
                "ip_address": {"$first": "$ip_address"},
                "username": {"$first": "$username"},
                "platform": {"$first": "$platform"},
                "browser": {"$first": "$browser"},
                "version": {"$first": "$version"},
                "mobile": {"$first": "$mobile"},
            }
        },
        {"$sort": {"last_visit": -1}}
    ]

    summary = list(visits_col.aggregate(pipeline))
    for item in summary:
        item["user_id"] = item.pop("_id")
        if isinstance(item["last_visit"], datetime):
            item["last_visit"] = item["last_visit"].isoformat()

    return jsonify({"summary": summary})

@app.route('/visits/<user_id>', methods=['GET'])
def get_visits_by_user(user_id):
    visits = list(visits_col.find({"user_id": user_id}).sort("timestamp", -1))
    for visit in visits:
        visit["_id"] = str(visit["_id"])
        if isinstance(visit["timestamp"], datetime):
            visit["timestamp"] = visit["timestamp"].isoformat()
    return jsonify({"visits": visits})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

