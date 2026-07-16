FROM python:3.11-slim

WORKDIR /app

# Install deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY app/ app/
COPY static/ static/
COPY run.py .

# Uploads dir
RUN mkdir -p uploads

EXPOSE 8502

# Run with waitress for production
ENV PORT=8502
CMD ["python", "-m", "waitress", "--host=0.0.0.0", "--port=8502", "--call", "app:create_app"]
# Alternative if waitress not wanted:
# CMD ["python", "run.py"]
