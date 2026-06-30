# myEnergy — production container.
# scipy/numpy ship prebuilt manylinux wheels for CPython 3.11, so no compilers
# are needed on the slim base — pip just downloads wheels.
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first so this layer is cached unless requirements change.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application (backend + frontend + the validated simulation engine).
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY simulation/ ./simulation/

# main.py imports its sibling modules as top-level names, so run from backend/.
# Paths to ../frontend, ../simulation and ../data are __file__-relative, so they
# resolve correctly regardless of the host. The data dir is created at runtime.
WORKDIR /app/backend

# Hosts (Render, Fly, Cloud Run...) inject the port via $PORT; default to 8000.
ENV PORT=8000
EXPOSE 8000

# Shell form so ${PORT} expands at runtime.
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --loop asyncio --http h11
