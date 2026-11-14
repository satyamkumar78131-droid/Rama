# Rama 🙏

Rama — apna AI chat app. FastAPI backend + React/Vite frontend. Zero se banaya gaya.

## Features

- **AI chat** — Gemini (gemini-2.0-flash) se jawab, step-by-step reasoning
- **Memory pehle** — saved yaadein (jaise "mera naam Satyam hai") web search se pehle aati hain; naam wale sawal kabhi web search nahi karte
- **Web search** — DuckDuckGo + Wikipedia (koi API key nahi chahiye)
- **File upload** — .txt / .md / .csv padh ke memory me save karta hai (PDF support nahi hai)
- **Conversations + Memories** — SQLite me save hote hain, restart ke baad bhi rehte hain

## Structure

```
Rama/
├── backend/        # FastAPI (Python)
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── database.py
│   ├── ai_router.py
│   ├── memory.py
│   ├── web_search.py
│   ├── file_reader.py
│   └── security.py
├── frontend/       # React + Vite
│   ├── package.json
│   ├── index.html
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── styles.css
│       └── components/
├── .gitignore
└── README.md
```

## Deploy

### Backend — Render (Free)
- Service: Rama (Python 3)
- Branch: main
- **Root Directory: backend**
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Environment Variable: `GEMINI_API_KEY` (Render dashboard me daalo — kabhi GitHub pe mat daalo)
- Health check: `GET /health` → `{"status": "healthy"}`

### Frontend — Vercel
- Repository: Rama
- **Root Directory: frontend**
- Framework: Vite
- Environment Variable: `VITE_API_BASE_URL=https://rama-qw4a.onrender.com`

## Backend chalao (local)

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# .env me apni GEMINI_API_KEY daalo
uvicorn main:app --reload --app-dir backend
```

Backend chalega: http://localhost:8000

## Frontend chalao

```bash
cd frontend
npm install
npm run dev
```

Frontend chalega: http://localhost:5173

## Notes

- Gemini key bina backend chalega, lekin AI jawab ke liye key chahiye (web search bina key ke bhi kaam karta hai).
- Prod me CORS origins ko restrict karo (backend/security.py me `CORS_ORIGINS`).
