from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv
from flask_cors import CORS
import os

load_dotenv()

app = Flask(__name__)
CORS(app, origins=["http://localhost:4200", "https://ryanbeevers.github.io/my-resume-app"])

try:
    client = MongoClient(os.environ.get("MONGO_URI"), serverSelectionTimeoutMS=5000)
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

@app.route('/progress/star', methods=['POST'])
def add_star():
    data = request.json
    user_id = data.get("user_id")
    star_id = data.get("star_id")

    if not user_id or not star_id:
        return jsonify({"error": "Missing user_id or star_id"}), 400

    result = progress_col.update_one(
        {"user_id": user_id},
        {
            "$addToSet": {"stars_found": star_id},
            "$set": {"last_updated": datetime.utcnow()}
        },
        upsert=True
    )

    return jsonify({"status": "star added", "modified_count": result.modified_count})

@app.route('/progress/<user_id>', methods=['GET'])
def get_progress(user_id):
    progress = progress_col.find_one({"user_id": user_id}, {"_id": 0})
    if not progress:
        return jsonify({"stars_found": []})
    return jsonify(progress)

if __name__ == '__main__':
    app.run(debug=True)
