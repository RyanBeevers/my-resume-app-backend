from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv
from flask_cors import CORS
import certifi
import os

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["http://localhost:4200", "https://ryanbeevers.github.io"])

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
    visit = {
        "user_id": data.get("user_id"),
        "ip_address": request.remote_addr,
        "user_agent": request.headers.get('User-Agent'),
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

    if updated_stars == all_star_ids:
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


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

