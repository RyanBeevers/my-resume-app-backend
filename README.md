# Resume Backend (Flask + MongoDB)

This is a simple backend service for tracking visits and gamification progress on a resume website.

## Features
- Track visits (IP, User-Agent, time)
- Log gamification events (e.g., found stars)
- Fetch progress per user

## Stack
- Python + Flask
- MongoDB (Atlas)
- Hostable on Render, Fly.io, or similar

## Setup

1. Install dependencies:
```
pip install -r requirements.txt
```

2. Add a `.env` file with your Mongo URI:
```
MONGO_URI=mongodb+srv://your_user:your_pass@cluster.mongodb.net/?retryWrites=true&w=majority
```

3. Run the app:
```
python app.py
```

4. Use an HTTP client (or frontend JS) to hit:
- `POST /track-visit`
- `POST /progress`
- `GET /progress/<user_id>`
