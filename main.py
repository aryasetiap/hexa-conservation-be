from typing import Annotated
from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import geopandas
import json
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

app = FastAPI()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_SERVICE_KEY")
supabase: Client = create_client(url, key)

token_auth_scheme = HTTPBearer()

async def get_current_user(token: Annotated[HTTPAuthorizationCredentials, Depends(token_auth_scheme)]):
    try:
        user_response = supabase.auth.get_user(token.credentials)
        user = user_response.user
        if not user:
            raise HTTPException(status_code=401, detail="Invalid authentication credentials")
        return user
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/buffer")
async def buffer(
    current_user: Annotated[dict, Depends(get_current_user)],
    geojson_polygon: UploadFile = File(...),
    buffer_value: int = Form(...)
):
    print(f"Request received from authenticated user: {current_user.id}")
    
    gdf = geopandas.read_file(geojson_polygon.file)
    gdf_project = gdf.to_crs(3395)
    gdf_buffer = gdf_project.buffer(buffer_value).to_crs(4326)
    return json.loads(gdf_buffer.to_json())
