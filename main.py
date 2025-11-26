from typing import Annotated
from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import geopandas
import json
import os
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client, Client
import io
import zipfile
import tempfile
import shutil

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

def read_zip_shapefile_in_memory(file_content: bytes) -> geopandas.GeoDataFrame:    
    temp_dir = tempfile.mkdtemp()
    try:
        bytes_io = io.BytesIO(file_content)
        with zipfile.ZipFile(bytes_io, 'r') as zf:
            zf.extractall(temp_dir)

        shp_path = None
        for root, dirs, files in os.walk(temp_dir):
            for file in files:
                if file.endswith('.shp'):
                    shp_path = os.path.join(root, file)
                    break
            if shp_path:
                break
        
        if not shp_path:
            raise HTTPException(status_code=400, detail="No .shp file found in the zip archive.")

        gdf = geopandas.read_file(shp_path)
        return gdf

    finally:
        shutil.rmtree(temp_dir)


@app.get("/")
def read_root():
    return {"Hello": "World"}

# Endpoint Stage 2
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

# Endpoint Stage 6 
@app.post("/process")
async def process_geospatial(
    current_user: Annotated[dict, Depends(get_current_user)],
    operation: str = Form(...),
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(None)
):
    try:
        gdf_a = read_zip_shapefile_in_memory(await file_a.read())
        gdf_a = gdf_a.to_crs("EPSG:3395")
        
        result_gdf = None

        if operation in ["clip", "difference", "union", "intersect", "merge"]:
            if not file_b:
                raise HTTPException(status_code=400, detail=f"Operation '{operation}' requires two files.")
            gdf_b = read_zip_shapefile_in_memory(await file_b.read())
            gdf_b = gdf_b.to_crs("EPSG:3395")

            if operation == "clip":
                result_gdf = geopandas.clip(gdf_a, gdf_b)
            elif operation == "difference":
                b_unary = gdf_b.unary_union
                result_gdf = gdf_a.difference(b_unary)
                result_gdf = geopandas.GeoDataFrame(geometry=result_gdf, crs="EPSG:3395")
            elif operation == "union":
                a_unary = gdf_a.unary_union
                b_unary = gdf_b.unary_union
                result_gdf = a_unary.union(b_unary)
                result_gdf = geopandas.GeoDataFrame(geometry=[result_gdf], crs="EPSG:3395")
            elif operation == "intersect":
                result_gdf = geopandas.overlay(gdf_a, gdf_b, how='intersection')
            elif operation == "merge":
                result_gdf = pd.concat([gdf_a, gdf_b], ignore_index=True)
        
        elif operation == "dissolve":
            result_gdf = gdf_a.dissolve()
        
        else:
            raise HTTPException(status_code=400, detail=f"Operation '{operation}' not supported.")

        if result_gdf is None or result_gdf.empty:
            raise HTTPException(status_code=404, detail="The operation resulted in an empty geometry.")

        result_gdf = result_gdf.to_crs("EPSG:4326")
        
        return json.loads(result_gdf.to_json())

    except Exception as e:
        print(f"Error during processing: {e}")
        raise HTTPException(status_code=500, detail=str(e))
