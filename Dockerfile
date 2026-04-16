FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source files
COPY . .

# Data directory (mounted as Fly volume in production)
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

EXPOSE 7771

CMD ["python", "main.py"]
