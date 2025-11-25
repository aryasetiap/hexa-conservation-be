from typing import Union, Annotated
from fastapi import FastAPI, File, UploadFile, Form
import geopandas
import geodatasets
import json

app = FastAPI()


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.post("/buffer")
async def buffer(geojson_polygon: UploadFile = File(...), buffer_value: int = Form(...)):
    gdf = geopandas.read_file(geojson_polygon.file)
    gdf_project = gdf.to_crs(3395)
    # gdf_project = geopandas.GeoDataFrame(gdf, crs="EPSG:3395")
    gdf_buffer = gdf_project.buffer(buffer_value).to_crs(4326)
    # return JSONResponse(gdf_buffer)
    return json.loads(gdf_buffer.to_json())
