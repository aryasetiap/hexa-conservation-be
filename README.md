# Hexa Conservation - Backend API

Backend service for geospatial processing built with FastAPI.

## Setup (Recommended: uv)

This project uses `uv` for fast environment and package management.

1.  **Install uv:**

    ```sh
    pip install uv
    ```

2.  **Create and activate virtual environment:**

    ```sh
    uv venv
    source .venv/bin/activate
    ```

3.  **Install dependencies:**

    ```sh
    uv pip install -r requirements.txt
    ```

4.  **Run the development server:**
    ```sh
    uvicorn main:app --reload
    ```
