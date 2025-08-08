FROM python:3.11-slim

WORKDIR /app

# Install uv for faster dependency management
RUN pip install uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen

# Copy application code
COPY bot/ ./bot/
COPY .env* ./

# Create data directory for database
RUN mkdir -p data

# Declare volume for database persistence
VOLUME ["/app/data"]

# Run the bot
CMD ["uv", "run", "python", "-m", "bot"]