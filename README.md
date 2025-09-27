# AI Resume Matcher MVP

This project helps recruiters efficiently shortlist resumes against job descriptions using AI.

## How to Run the Project

### 1. Start the Database (Weaviate)

Navigate to the db directory and run Docker Compose:

```bash
cd db
docker-compose up -d
```

You can access the Weaviate instance at [http://localhost:8080](http://localhost:8080).

### 2. Run the Backend Server

Navigate to the backend directory, activate the virtual environment, and start the FastAPI server:

```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API will be available at [http://127.0.0.1:8000](http://127.0.0.1:8000).

### 3. Run the Frontend Application

Navigate to the frontend directory, install dependencies, and start the React development server:

```bash
cd frontend
npm install
npm start
```

The application will open automatically at [http://localhost:3000](http://localhost:3000).
