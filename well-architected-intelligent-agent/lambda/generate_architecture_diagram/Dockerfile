FROM python:3.9-slim

# Install system dependencies including Graphviz and debugging tools
RUN apt-get update && apt-get install -y \
    graphviz \
    graphviz-dev \
    pkg-config \
    curl \
    jq \
    procps \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Verify Graphviz installation
RUN dot -V

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a directory for temporary files
RUN mkdir -p /tmp/diagrams && chmod 777 /tmp/diagrams

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=8080 \
    S3_BUCKET=minigrammer-output \
    LOG_LEVEL=DEBUG \
    PYTHONPATH=/app

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "app.py"]