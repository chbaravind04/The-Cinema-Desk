import os
import json
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import google.auth
from google.auth.transport.requests import Request

PROJECT_ID = "665386762151"
LOCATION = "us-west1"
ENGINE_ID = "119701631892717568"
STREAM_URL = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/reasoningEngines/{ENGINE_ID}:streamQuery?alt=sse"

credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])

def get_auth_token():
    if not credentials.valid:
        credentials.refresh(Request())
    return credentials.token

app = FastAPI(title="The Cinema Desk Gateway")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the web app on root URL
@app.get("/")
async def serve_index():
    return FileResponse("static/index.html")

class QueryRequest(BaseModel):
    message: str
    user_id: str = "web_user"

@app.post("/api/chat")
async def chat(request: QueryRequest):
    try:
        token = get_auth_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        payload = {
            "class_method": "async_stream_query",
            "input": {
                "user_id": request.user_id,
                "message": request.message
            }
        }
        
        collected_text = []
        async with httpx.AsyncClient(timeout=180.0) as client:
            async with client.stream("POST", STREAM_URL, headers=headers, json=payload) as response:
                if response.status_code != 200:
                    err_body = await response.aread()
                    raise HTTPException(status_code=response.status_code, detail=err_body.decode())
                
                async for line in response.aiter_lines():
                    clean_line = line.strip()
                    if not clean_line:
                        continue
                    if clean_line.startswith("data:"):
                        clean_line = clean_line[5:].strip()
                    if not clean_line:
                        continue
                        
                    try:
                        event = json.loads(clean_line)
                        content = event.get("content", {})
                        if isinstance(content, dict):
                            parts = content.get("parts", [])
                            for part in parts:
                                if isinstance(part, dict) and "text" in part:
                                    t = part["text"]
                                    if t:
                                        collected_text.append(t)
                    except Exception:
                        pass
        
        final_answer = "".join(collected_text).strip()
        if not final_answer:
            final_answer = "I processed your request, but could not format the output."
            
        return {"response": final_answer}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
