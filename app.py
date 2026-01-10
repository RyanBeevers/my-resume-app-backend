from flask import Flask, request, jsonify, send_file
from pymongo import MongoClient
from datetime import datetime
from pymongo.errors import ServerSelectionTimeoutError
from dotenv import load_dotenv
from flask_cors import CORS
from user_agents import parse
import certifi
import os
import subprocess
from docx import Document

load_dotenv()

app = Flask(__name__)
CORS(app, origins=[os.environ.get("NGROK_URL"), "http://localhost:4200", "https://ryanbeevers.github.io*", "http://raspberrypi.local:4200"])

LLAMA_BIN = "/home/ryan2914/llama.cpp/build/bin/llama-run"
MODEL_PATH = "file:///home/ryan2914/llama.cpp/models/tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"

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

@app.route('/generate', methods=['POST'])
def generate_resume_text():
    data = request.json
    prompt = data.get("prompt", "")
    if not prompt:
        return jsonify({"error": "Missing prompt"}), 400

    try:
        result = subprocess.run(
            [LLAMA_BIN, MODEL_PATH, prompt],
            capture_output=True, text=True, timeout=300
        )
        return jsonify({"response": result.stdout.strip()})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Model timed out"}), 504
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

# Replace a single placeholder in doc
def replace_placeholder(doc, placeholder, replacement):
    for paragraph in doc.paragraphs:
        if placeholder in paragraph.text:
            paragraph.text = paragraph.text.replace(placeholder, replacement)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if placeholder in cell.text:
                    cell.text = cell.text.replace(placeholder, replacement)
    return doc

# Add bulleted list under a placeholder
def add_bullets(doc, placeholder, bullets):
    for paragraph in doc.paragraphs:
        if placeholder in paragraph.text:
            parent = paragraph._element
            for b in bullets:
                doc.add_paragraph(b, style='List Bullet')
            paragraph.text = ''  # remove placeholder
    return doc

def build_resume(json_data, template_path, output_path):
    doc = Document(template_path)

    # Replace header & summary
    doc = replace_placeholder(doc, '{{NAME}}', json_data['resume']['header']['name'])
    doc = replace_placeholder(doc, '{{TITLE}}', json_data['resume']['header']['title'])
    doc = replace_placeholder(doc, '{{TAGLINE}}', json_data['resume']['header']['tagline'])
    doc = replace_placeholder(doc, '{{LOCATION_NOTE}}', json_data['resume']['header']['location_note'])
    doc = replace_placeholder(doc, '{{SUMMARY}}', json_data['resume']['summary'])

    # Experience
    for idx, exp in enumerate(json_data['resume']['experience']):
        placeholder = f'{{EXP_{idx+1}}}'
        exp_text = f"{exp['company']}, {exp['role']} ({exp['dates']})"
        doc = replace_placeholder(doc, placeholder, exp_text)
        doc = add_bullets(doc, placeholder, exp['bullets'])

    # Skills
    skills = json_data['resume']['skills']
    doc = replace_placeholder(doc, '{{FRONTEND_SKILLS}}', ', '.join(skills.get('frontend', [])))
    doc = replace_placeholder(doc, '{{BACKEND_SKILLS}}', ', '.join(skills.get('backend', [])))
    doc = replace_placeholder(doc, '{{CLOUD_DEVOPS_SKILLS}}', ', '.join(skills.get('cloud_devops', [])))
    doc = replace_placeholder(doc, '{{SECURITY_AUTH_SKILLS}}', ', '.join(skills.get('security_auth', [])))
    doc = replace_placeholder(doc, '{{DATABASE_SKILLS}}', ', '.join(skills.get('databases', [])))
    doc = replace_placeholder(doc, '{{TOOLS_SKILLS}}', ', '.join(skills.get('tools_collaboration', [])))

    doc.save(output_path)
    return output_path

def build_cover_letter(json_data, template_path, output_path):
    doc = Document(template_path)

    # Recipient
    doc = replace_placeholder(doc, '{{COMPANY}}', json_data['cover_letter']['recipient']['company'])
    doc = replace_placeholder(doc, '{{ROLE}}', json_data['cover_letter']['recipient']['role'])

    # Body paragraphs
    doc = replace_placeholder(doc, '{{OPENING_PARAGRAPH}}', json_data['cover_letter']['opening_paragraph'])
    for i, para in enumerate(json_data['cover_letter']['body_paragraphs']):
        placeholder = f'{{BODY_PARAGRAPH_{i+1}}}'
        doc = replace_placeholder(doc, placeholder, para)

    # Closing & signature
    doc = replace_placeholder(doc, '{{CLOSING_PARAGRAPH}}', json_data['cover_letter']['closing_paragraph'])
    doc = replace_placeholder(doc, '{{NAME}}', json_data['cover_letter']['signature']['name'])

    doc.save(output_path)
    return output_path

from flask import Flask, request, send_file


@app.route('/generate_docs', methods=['POST'])
def generate_docs():
    data = request.json  # {resume: {...}, cover_letter: {...}}

    resume_path = build_resume(data['resume'], 'templates/resume_template.docx', 'outputs/resume.docx')
    cover_path = build_cover_letter(data['cover_letter'], 'templates/cover_letter_template.docx', 'outputs/cover_letter.docx')

    return {
        'resume_path': resume_path,
        'cover_letter_path': cover_path
    }
