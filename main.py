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
def health_check():
    """Endpoint untuk health check dari Render."""
    return {"status": "ok", "message": "API is running"}

# Endpoint Stage 2 (Diperbarui untuk Stage 7)
@app.post("/buffer")
async def buffer(
    current_user: Annotated[dict, Depends(get_current_user)],
    geojson_polygon: UploadFile = File(...),
    buffer_value: int = Form(...)
):
    try:
        print(f"Request received from authenticated user: {current_user.id}")
        
        # Baca GeoJSON. Asumsikan inputnya dalam EPSG:4326 (standar web)
        gdf = geopandas.read_file(geojson_polygon.file)
        if gdf.crs is None:
            # Jika CRS tidak ada, asumsikan EPSG:4326
            gdf.set_crs("EPSG:4326", inplace=True)
        else:
            # Jika ada, pastikan itu EPSG:4326
            gdf = gdf.to_crs("EPSG:4326")

        # --- Logika Inti Stage 7 ---
        # 1. Estimasi CRS UTM yang paling sesuai untuk poligon 
        # Melihat pusat dari geometri
        utm_crs = gdf.estimate_utm_crs()
        print(f"Detected optimal UTM CRS: {utm_crs.to_string()}")

        # 2. Proyeksikan ke CRS UTM yang terdeteksi untuk operasi buffer yang akurat
        gdf_projected = gdf.to_crs(utm_crs)

        # 3. Lakukan buffer dalam satuan meter pada sistem proyeksi UTM
        gdf_buffered_projected = gdf_projected.buffer(buffer_value)

        # 4. Proyeksikan kembali hasilnya ke EPSG:4326 agar bisa ditampilkan di peta Leaflet
        gdf_buffer_final = gdf_buffered_projected.to_crs("EPSG:4326")
        
        # Ubah hasil GeoSeries menjadi GeoDataFrame sebelum diekspor ke JSON
        result_gdf = geopandas.GeoDataFrame(geometry=gdf_buffer_final, crs="EPSG:4326")

        return json.loads(result_gdf.to_json())

    except Exception as e:
        print(f"Error during buffer processing: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred: {str(e)}")


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
