# Use Python 3.11 (stable for discord.py + PyNaCl)
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && apt-get clean

# Set working directory
WORKDIR /app

# Copy requirement list first for caching
COPY requirements.txt .

# Install python requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy bot code
COPY . .

# Run the bot
CMD ["python", "main.py"]
